from django.core.management.base import BaseCommand

from fitness.models import Exercise, ExercisePattern


EXERCISES = [
    # Push
    {"name": "Bench Press", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Incline Dumbbell Press", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Chest Press Machine", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Seated Dumbbell Shoulder Press", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Lateral Raise", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Cable Fly", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Triceps Pushdown", "primary_pattern": ExercisePattern.PUSH},
    {"name": "Overhead Triceps Extension", "primary_pattern": ExercisePattern.PUSH},

    # Pull
    {"name": "Lat Pulldown", "primary_pattern": ExercisePattern.PULL},
    {"name": "Pull-Up", "primary_pattern": ExercisePattern.PULL},
    {"name": "Chest Supported Row", "primary_pattern": ExercisePattern.PULL},
    {"name": "Seated Cable Row", "primary_pattern": ExercisePattern.PULL},
    {"name": "Barbell Row", "primary_pattern": ExercisePattern.PULL},
    {"name": "Dumbbell Row", "primary_pattern": ExercisePattern.PULL},
    {"name": "Face Pull", "primary_pattern": ExercisePattern.PULL},
    {"name": "Barbell Curl", "primary_pattern": ExercisePattern.PULL},
    {"name": "Incline Dumbbell Curl", "primary_pattern": ExercisePattern.PULL},
    {"name": "Hammer Curl", "primary_pattern": ExercisePattern.PULL},

    # Legs
    {"name": "Barbell Squat", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Hack Squat", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Leg Press", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Romanian Deadlift", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Leg Extension", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Leg Curl", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Walking Lunge", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Standing Calf Raise", "primary_pattern": ExercisePattern.LEGS},
    {"name": "Seated Calf Raise", "primary_pattern": ExercisePattern.LEGS},

    # Core
    {"name": "Cable Crunch", "primary_pattern": ExercisePattern.CORE},
    {"name": "Hanging Leg Raise", "primary_pattern": ExercisePattern.CORE},
    {"name": "Plank", "primary_pattern": ExercisePattern.CORE},

    # Cardio / Other
    {"name": "Treadmill Walk", "primary_pattern": ExercisePattern.CARDIO},
    {"name": "Stationary Bike", "primary_pattern": ExercisePattern.CARDIO},
    {"name": "Elliptical", "primary_pattern": ExercisePattern.CARDIO},
]


class Command(BaseCommand):
    help = "Seed default global exercises."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for item in EXERCISES:
            exercise, created = Exercise.objects.update_or_create(
                created_by=None,
                slug="",
                name=item["name"],
                defaults={
                    "primary_pattern": item["primary_pattern"],
                    "is_active": True,
                    "is_custom": False,
                },
            )

            if not exercise.slug:
                exercise.save(update_fields=["slug", "updated_at"])

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete. Created: {created_count}, updated: {updated_count}"
            )
        )