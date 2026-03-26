from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from .forms import (
    ExerciseForm,
    ExercisePoolForm,
    ExercisePoolItemForm,
    WorkoutSessionExerciseForm,
    WorkoutSessionForm,
    WorkoutSetForm,
)
from .models import (
    Exercise,
    ExercisePool,
    ExercisePoolItem,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
    WorkoutSet,
)


def get_session_queryset(user):
    return (
        WorkoutSession.objects.filter(user=user)
        .select_related("source_pool")
        .prefetch_related(
            Prefetch(
                "session_exercises",
                queryset=WorkoutSessionExercise.objects.select_related("exercise", "source_pool_item")
                .prefetch_related(
                    Prefetch("sets", queryset=WorkoutSet.objects.order_by("set_order", "id"))
                )
                .order_by("sequence", "id"),
            )
        )
    )


def attach_session_forms(session):
    session.add_exercise_form = WorkoutSessionExerciseForm(session=session)

    for entry in session.session_exercises.all():
        entry.add_set_form = WorkoutSetForm(
            session_exercise=entry,
            prefix=f"set-{entry.pk}",
        )

        for workout_set in entry.sets.all():
            workout_set.edit_form = WorkoutSetForm(
                instance=workout_set,
                prefix=f"edit-set-{workout_set.pk}",
            )

        previous_entry = (
            WorkoutSessionExercise.objects.select_related("session", "exercise")
            .prefetch_related(
                Prefetch("sets", queryset=WorkoutSet.objects.order_by("set_order", "id"))
            )
            .filter(
                exercise=entry.exercise,
                session__user=session.user,
                session__status=WorkoutSessionStatus.COMPLETED,
            )
            .exclude(session=session)
            .order_by("-session__started_at", "-session__created_at", "-id")
            .first()
        )

        entry.previous_entry = previous_entry

        best_set = (
            WorkoutSet.objects.filter(
                session_exercise__exercise=entry.exercise,
                session_exercise__session__user=session.user,
                weight_kg__isnull=False,
            )
            .order_by("-weight_kg", "-reps")
            .first()
        )

        last_set = previous_entry.sets.order_by("-set_order").first() if previous_entry else None

        entry.best_set = best_set
        entry.last_set = last_set

    return session


def render_session_exercises_partial(request, session):
    session = attach_session_forms(session)
    return render(
        request,
        "fitness/partials/session_exercises.html",
        {"session": session},
    )

def render_session_header_partial(request, session):
    header_form = WorkoutSessionForm(instance=session, user=session.user)
    return render(
        request,
        "fitness/partials/session_header.html",
        {
            "session": session,
            "header_form": header_form,
        },
    )

class ExerciseListView(LoginRequiredMixin, ListView):
    model = Exercise
    template_name = "fitness/exercise_list.html"
    context_object_name = "exercises"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            Exercise.objects.filter(is_active=True)
            .filter(Q(created_by__isnull=True) | Q(created_by=self.request.user))
            .select_related("created_by")
            .order_by("name", "id")
        )
        pattern = self.request.GET.get("pattern")
        if pattern:
            queryset = queryset.filter(primary_pattern=pattern)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_pattern"] = self.request.GET.get("pattern", "")
        context["pattern_choices"] = Exercise._meta.get_field("primary_pattern").choices
        return context


class ExerciseCreateView(LoginRequiredMixin, View):
    template_name = "fitness/exercise_form.html"

    def get(self, request):
        form = ExerciseForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ExerciseForm(request.POST)
        if form.is_valid():
            exercise = form.save(commit=False)
            exercise.created_by = request.user
            exercise.save()
            return redirect("fitness:exercise-list")
        return render(request, self.template_name, {"form": form})

class ExerciseUpdateView(LoginRequiredMixin, View):
    template_name = "fitness/exercise_edit_form.html"

    def get_exercise(self, request, pk):
        return get_object_or_404(
            Exercise,
            pk=pk,
            created_by=request.user,
        )

    def get(self, request, pk):
        exercise = self.get_exercise(request, pk)
        form = ExerciseForm(instance=exercise)
        return render(request, self.template_name, {"exercise": exercise, "form": form})

    def post(self, request, pk):
        exercise = self.get_exercise(request, pk)
        form = ExerciseForm(request.POST, instance=exercise)

        if form.is_valid():
            updated_exercise = form.save(commit=False)
            updated_exercise.created_by = request.user
            updated_exercise.save()
            return redirect("fitness:exercise-list")

        return render(request, self.template_name, {"exercise": exercise, "form": form})


class ExerciseDeactivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        exercise = get_object_or_404(
            Exercise,
            pk=pk,
            created_by=request.user,
        )
        exercise.is_active = False
        exercise.save(update_fields=["is_active", "updated_at"])
        return redirect("fitness:exercise-list")


class ExercisePoolListView(LoginRequiredMixin, ListView):
    model = ExercisePool
    template_name = "fitness/pool_list.html"
    context_object_name = "pools"

    def get_queryset(self):
        return (
            ExercisePool.objects.filter(user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=ExercisePoolItem.objects.select_related("exercise").order_by("sequence", "id"),
                )
            )
            .order_by("name", "id")
        )


class ExercisePoolCreateView(LoginRequiredMixin, View):
    template_name = "fitness/pool_form.html"

    def get(self, request):
        form = ExercisePoolForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ExercisePoolForm(request.POST)
        if form.is_valid():
            pool = form.save(commit=False)
            pool.user = request.user
            pool.save()
            return redirect("fitness:pool-detail", pk=pool.pk)
        return render(request, self.template_name, {"form": form})

class ExercisePoolUpdateView(LoginRequiredMixin, View):
    template_name = "fitness/pool_edit_form.html"

    def get_pool(self, request, pk):
        return get_object_or_404(ExercisePool, pk=pk, user=request.user)

    def get(self, request, pk):
        pool = self.get_pool(request, pk)
        form = ExercisePoolForm(instance=pool)
        return render(request, self.template_name, {"pool": pool, "form": form})

    def post(self, request, pk):
        pool = self.get_pool(request, pk)
        form = ExercisePoolForm(request.POST, instance=pool)

        if form.is_valid():
            form.save()
            return redirect("fitness:pool-detail", pk=pool.pk)

        return render(request, self.template_name, {"pool": pool, "form": form})


class ExercisePoolDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pool = get_object_or_404(ExercisePool, pk=pk, user=request.user)
        pool.delete()
        return redirect("fitness:pool-list")

class ExercisePoolDetailView(LoginRequiredMixin, View):
    template_name = "fitness/pool_detail.html"

    def get(self, request, pk):
        pool = get_object_or_404(
            ExercisePool.objects.filter(user=request.user).prefetch_related(
                Prefetch(
                    "items",
                    queryset=ExercisePoolItem.objects.select_related("exercise").order_by("sequence", "id"),
                )
            ),
            pk=pk,
        )
        return render(request, self.template_name, {"pool": pool})


class ExercisePoolAddExerciseView(LoginRequiredMixin, View):
    template_name = "fitness/pool_add_exercise.html"

    def get_pool(self, request, pk):
        return get_object_or_404(ExercisePool, pk=pk, user=request.user)

    def get(self, request, pk):
        pool = self.get_pool(request, pk)
        form = ExercisePoolItemForm(pool=pool)
        return render(request, self.template_name, {"pool": pool, "form": form})

    def post(self, request, pk):
        pool = self.get_pool(request, pk)
        form = ExercisePoolItemForm(request.POST, pool=pool)

        if form.is_valid():
            item = form.save(commit=False)
            item.pool = pool
            item.save()
            return redirect("fitness:pool-detail", pk=pool.pk)

        return render(request, self.template_name, {"pool": pool, "form": form})


class WorkoutSessionListView(LoginRequiredMixin, ListView):
    model = WorkoutSession
    template_name = "fitness/session_list.html"
    context_object_name = "sessions"

    def get_queryset(self):
        return (
            WorkoutSession.objects.filter(user=self.request.user)
            .select_related("source_pool")
            .order_by("-created_at", "-id")
        )


class WorkoutSessionCreateView(LoginRequiredMixin, View):
    template_name = "fitness/session_form.html"

    def get(self, request):
        form = WorkoutSessionForm(user=request.user)
        return render(request, self.template_name, {"form": form})

    @transaction.atomic
    def post(self, request):
        form = WorkoutSessionForm(request.POST, user=request.user)

        if form.is_valid():
            session = form.save(commit=False)
            session.user = request.user
            session.save()

            source_pool = session.source_pool
            if source_pool:
                pool_items = source_pool.items.filter(is_active=True).select_related("exercise").order_by("sequence", "id")
                session_exercises = [
                    WorkoutSessionExercise(
                        session=session,
                        exercise=item.exercise,
                        sequence=item.sequence,
                        source_pool_item=item,
                    )
                    for item in pool_items
                ]
                if session_exercises:
                    WorkoutSessionExercise.objects.bulk_create(session_exercises)

            return redirect("fitness:session-detail", pk=session.pk)

        return render(request, self.template_name, {"form": form})


class WorkoutSessionDetailView(LoginRequiredMixin, View):
    template_name = "fitness/session_detail.html"

    def get(self, request, pk):
        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        session = attach_session_forms(session)
        header_form = WorkoutSessionForm(instance=session, user=request.user)
        return render(
            request,
            self.template_name,
            {
                "session": session,
                "header_form": header_form,
            },
        )


class WorkoutSessionAddExerciseView(LoginRequiredMixin, View):
    template_name = "fitness/session_add_exercise.html"

    def get_session(self, request, pk):
        return get_object_or_404(WorkoutSession, pk=pk, user=request.user)

    def get(self, request, pk):
        session = self.get_session(request, pk)
        form = WorkoutSessionExerciseForm(session=session)
        return render(request, self.template_name, {"session": session, "form": form})

    def post(self, request, pk):
        session = self.get_session(request, pk)
        form = WorkoutSessionExerciseForm(request.POST, session=session)

        if form.is_valid():
            next_sequence = (
                session.session_exercises.order_by("-sequence").values_list("sequence", flat=True).first() or 0
            ) + 1

            session_exercise = form.save(commit=False)
            session_exercise.session = session
            session_exercise.sequence = next_sequence
            session_exercise.save()
            return redirect("fitness:session-detail", pk=session.pk)

        return render(request, self.template_name, {"session": session, "form": form})

class WorkoutSessionDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)
        session.delete()
        return redirect("fitness:session-list")

class WorkoutSetCreateView(LoginRequiredMixin, View):
    template_name = "fitness/set_form.html"

    def get_session_exercise(self, request, session_pk, session_exercise_pk):
        return get_object_or_404(
            WorkoutSessionExercise.objects.select_related("session", "exercise"),
            pk=session_exercise_pk,
            session__pk=session_pk,
            session__user=request.user,
        )

    def get(self, request, session_pk, session_exercise_pk):
        session_exercise = self.get_session_exercise(request, session_pk, session_exercise_pk)
        form = WorkoutSetForm(session_exercise=session_exercise)
        return render(
            request,
            self.template_name,
            {"session_exercise": session_exercise, "form": form},
        )

    def post(self, request, session_pk, session_exercise_pk):
        session_exercise = self.get_session_exercise(request, session_pk, session_exercise_pk)
        form = WorkoutSetForm(request.POST, session_exercise=session_exercise)

        if form.is_valid():
            workout_set = form.save(commit=False)
            workout_set.session_exercise = session_exercise
            workout_set.save()
            return redirect("fitness:session-detail", pk=session_exercise.session_id)

        return render(
            request,
            self.template_name,
            {"session_exercise": session_exercise, "form": form},
        )


class HtmxWorkoutSessionAddExerciseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)
        form = WorkoutSessionExerciseForm(request.POST, session=session)

        if form.is_valid():
            next_sequence = (
                session.session_exercises.order_by("-sequence").values_list("sequence", flat=True).first() or 0
            ) + 1

            session_exercise = form.save(commit=False)
            session_exercise.session = session
            session_exercise.sequence = next_sequence
            session_exercise.save()

        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        return render_session_exercises_partial(request, session)


class HtmxWorkoutSessionDeleteExerciseView(LoginRequiredMixin, View):
    def post(self, request, pk, session_exercise_pk):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)

        session_exercise = get_object_or_404(
            WorkoutSessionExercise,
            pk=session_exercise_pk,
            session=session,
        )
        session_exercise.delete()

        # AUTO RESEQUENCE
        items = session.session_exercises.order_by("sequence", "id")
        for idx, item in enumerate(items, start=1):
            if item.sequence != idx:
                item.sequence = idx
                item.save(update_fields=["sequence"])

        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        return render_session_exercises_partial(request, session)


class HtmxWorkoutSetCreateView(LoginRequiredMixin, View):
    def post(self, request, session_pk, session_exercise_pk):
        session_exercise = get_object_or_404(
            WorkoutSessionExercise.objects.select_related("session"),
            pk=session_exercise_pk,
            session__pk=session_pk,
            session__user=request.user,
        )
        form = WorkoutSetForm(
            request.POST,
            session_exercise=session_exercise,
            prefix=f"set-{session_exercise.pk}",
        )

        if form.is_valid():
            next_order = (
                session_exercise.sets.order_by("-set_order").values_list("set_order", flat=True).first() or 0
            ) + 1

            workout_set = form.save(commit=False)
            workout_set.session_exercise = session_exercise
            workout_set.set_order = next_order
            workout_set.save()

        session = get_object_or_404(get_session_queryset(request.user), pk=session_pk)
        return render_session_exercises_partial(request, session)


class HtmxWorkoutSetDeleteView(LoginRequiredMixin, View):
    def post(self, request, session_pk, workout_set_pk):
        session = get_object_or_404(WorkoutSession, pk=session_pk, user=request.user)
        workout_set = get_object_or_404(
            WorkoutSet.objects.select_related("session_exercise"),
            pk=workout_set_pk,
            session_exercise__session=session,
        )
        session_exercise = workout_set.session_exercise
        workout_set.delete()

        # Auto-resequence set_order after delete
        sets = session_exercise.sets.order_by("set_order", "id")
        for idx, item in enumerate(sets, start=1):
            if item.set_order != idx:
                item.set_order = idx
                item.save(update_fields=["set_order"])

        session = get_object_or_404(get_session_queryset(request.user), pk=session_pk)
        return render_session_exercises_partial(request, session)

class HtmxWorkoutSetMoveView(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request, session_pk, workout_set_pk, direction):
        session = get_object_or_404(WorkoutSession, pk=session_pk, user=request.user)

        current = get_object_or_404(
            WorkoutSet.objects.select_related("session_exercise"),
            pk=workout_set_pk,
            session_exercise__session=session,
        )

        siblings = current.session_exercise.sets.all()

        if direction == "up":
            swap_with = (
                siblings.filter(set_order__lt=current.set_order)
                .order_by("-set_order")
                .first()
            )
        elif direction == "down":
            swap_with = (
                siblings.filter(set_order__gt=current.set_order)
                .order_by("set_order")
                .first()
            )
        else:
            return HttpResponseNotAllowed(["POST"])

        if swap_with:
            original_current_order = current.set_order
            original_swap_order = swap_with.set_order

            current.set_order = 0
            current.save(update_fields=["set_order"])

            swap_with.set_order = original_current_order
            swap_with.save(update_fields=["set_order"])

            current.set_order = original_swap_order
            current.save(update_fields=["set_order"])

        session = get_object_or_404(get_session_queryset(request.user), pk=session_pk)
        return render_session_exercises_partial(request, session)


class HtmxWorkoutSetResequenceView(LoginRequiredMixin, View):
    def post(self, request, session_pk, session_exercise_pk):
        session = get_object_or_404(WorkoutSession, pk=session_pk, user=request.user)

        session_exercise = get_object_or_404(
            WorkoutSessionExercise,
            pk=session_exercise_pk,
            session=session,
        )

        sets = session_exercise.sets.order_by("set_order", "id")
        for idx, item in enumerate(sets, start=1):
            if item.set_order != idx:
                item.set_order = idx
                item.save(update_fields=["set_order"])

        session = get_object_or_404(get_session_queryset(request.user), pk=session_pk)
        return render_session_exercises_partial(request, session)

class HtmxWorkoutSetUpdateView(LoginRequiredMixin, View):
    def post(self, request, session_pk, workout_set_pk):
        session = get_object_or_404(WorkoutSession, pk=session_pk, user=request.user)

        workout_set = get_object_or_404(
            WorkoutSet.objects.select_related("session_exercise"),
            pk=workout_set_pk,
            session_exercise__session=session,
        )

        form = WorkoutSetForm(
            request.POST,
            instance=workout_set,
            prefix=f"edit-set-{workout_set.pk}",
        )

        if form.is_valid():
            form.save()

        session = get_object_or_404(get_session_queryset(request.user), pk=session_pk)
        return render_session_exercises_partial(request, session)


class MethodNotAllowedView(View):
    def dispatch(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(permitted_methods=["GET", "POST"])

class HtmxWorkoutSessionMoveExerciseView(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk, session_exercise_pk, direction):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)

        current = get_object_or_404(
            WorkoutSessionExercise,
            pk=session_exercise_pk,
            session=session,
        )

        if direction == "up":
            swap_with = (
                session.session_exercises
                .filter(sequence__lt=current.sequence)
                .order_by("-sequence")
                .first()
            )
        elif direction == "down":
            swap_with = (
                session.session_exercises
                .filter(sequence__gt=current.sequence)
                .order_by("sequence")
                .first()
            )
        else:
            return HttpResponseNotAllowed(["POST"])

        if swap_with:
            original_current_sequence = current.sequence
            original_swap_sequence = swap_with.sequence

            # Temporary free slot to avoid unique constraint collision
            current.sequence = 0
            current.save(update_fields=["sequence"])

            swap_with.sequence = original_current_sequence
            swap_with.save(update_fields=["sequence"])

            current.sequence = original_swap_sequence
            current.save(update_fields=["sequence"])

        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        return render_session_exercises_partial(request, session)


class HtmxWorkoutSessionResequenceView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)

        items = session.session_exercises.order_by("sequence", "id")

        for idx, item in enumerate(items, start=1):
            if item.sequence != idx:
                item.sequence = idx
                item.save(update_fields=["sequence"])

        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        return render_session_exercises_partial(request, session)

class HtmxWorkoutSessionUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)
        form = WorkoutSessionForm(request.POST, instance=session, user=request.user)

        if form.is_valid():
            form.save()

        session = get_object_or_404(get_session_queryset(request.user), pk=pk)
        return render_session_header_partial(request, session)