from decimal import Decimal

import bio.models
import django.core.validators
import django_resized.forms
from django.conf import settings
from django.db import migrations, models


def backfill_profile_display_name(apps, schema_editor):
    Profile = apps.get_model("bio", "Profile")

    for profile in Profile.objects.select_related("user").all().iterator():
        if (profile.display_name or "").strip():
            continue

        full_name = (profile.full_name or "").strip()
        username = (getattr(profile.user, "username", "") or "").strip()
        email = (getattr(profile.user, "email", "") or "").strip()

        email_prefix = email.split("@", 1)[0].strip() if email else ""
        fallback = full_name or username or email_prefix or f"user-{profile.user_id}"

        profile.display_name = fallback[:50]
        profile.save(update_fields=["display_name"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bio', '0004_analyticssnapshot_last_enqueued_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='avatar',
            field=django_resized.forms.ResizedImageField(
                blank=True,
                crop=['middle', 'center'],
                force_format='WEBP',
                help_text='Allowed: jpg, jpeg, png, webp. Max size 2 MB. Stored as 512x512 WEBP.',
                keep_meta=True,
                null=True,
                quality=85,
                scale=None,
                size=[512, 512],
                upload_to=bio.models.avatar_upload_to,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
                    ),
                    bio.models.validate_avatar_file_size,
                ],
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='bio',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Short profile bio.',
                max_length=280,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='date_of_birth',
            field=models.DateField(
                blank=True,
                null=True,
                validators=[bio.models.validate_not_future_date],
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='display_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Primary app-facing nickname / display name.',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='goal_mode',
            field=models.CharField(
                choices=[
                    ('maintain', 'Maintain'),
                    ('lose_weight', 'Lose weight'),
                    ('gain_weight', 'Gain weight'),
                ],
                default='maintain',
                help_text='Primary user goal for onboarding and analytics.',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='height_cm',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Optional height in centimeters.',
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(80),
                    django.core.validators.MaxValueValidator(260),
                ],
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='onboarding_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='target_weight_kg',
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                help_text='Optional long-term target weight.',
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('25.0')),
                    django.core.validators.MaxValueValidator(Decimal('400.0')),
                ],
            ),
        ),
        migrations.RunPython(backfill_profile_display_name, noop_reverse),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['updated_at'], name='idx_profile_updated_at'),
        ),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['goal_mode'], name='idx_profile_goal_mode'),
        ),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['onboarding_completed_at'], name='idx_profile_onboarding_done'),
        ),
    ]