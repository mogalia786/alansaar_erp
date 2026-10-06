from django.db import migrations

NEW_SECTIONS = ['stall_changes', 'refunds', 'early_discounts']


def add_missing_role_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    RolePermission = apps.get_model('accounts', 'RolePermission')
    for role in Role.objects.all():
        for section in NEW_SECTIONS:
            RolePermission.objects.get_or_create(
                role=role, section=section,
                defaults={'can_view': True, 'can_create': False, 'can_edit': False, 'can_delete': False},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_rolepermission_section_alter_user_user_type'),
    ]

    operations = [
        migrations.RunPython(add_missing_role_permissions, migrations.RunPython.noop),
    ]
