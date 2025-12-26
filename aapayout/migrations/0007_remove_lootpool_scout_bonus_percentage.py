# Generated manually to fix database schema mismatch
# The database has a column 'scout_bonus_percentage' that doesn't exist in the model

from django.db import migrations, connection


def remove_column_if_exists(apps, schema_editor):
    """Remove scout_bonus_percentage column if it exists."""
    with connection.cursor() as cursor:
        # Check if column exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'aapayout_lootpool'
            AND column_name = 'scout_bonus_percentage'
        """)
        if cursor.fetchone()[0] > 0:
            cursor.execute("ALTER TABLE aapayout_lootpool DROP COLUMN scout_bonus_percentage")


def add_column_back(apps, schema_editor):
    """Add the column back for reverse migration."""
    with connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE aapayout_lootpool
            ADD COLUMN scout_bonus_percentage DECIMAL(5,2) NOT NULL DEFAULT 10.00
        """)


class Migration(migrations.Migration):

    dependencies = [
        ("aapayout", "0006_lootpool_scout_shares"),
    ]

    operations = [
        migrations.RunPython(remove_column_if_exists, add_column_back),
    ]
