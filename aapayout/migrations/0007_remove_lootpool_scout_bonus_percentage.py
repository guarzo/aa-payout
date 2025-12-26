# Generated manually to fix database schema mismatch
# The database has a column 'scout_bonus_percentage' that doesn't exist in the model

# Django
from django.db import connection, migrations


def remove_column_if_exists(apps, schema_editor):
    """Remove scout_bonus_percentage column if it exists."""
    # Get the table description using Django's introspection (database-agnostic)
    table_name = "aapayout_lootpool"
    with connection.cursor() as cursor:
        # Get column names using Django's introspection
        columns = [col.name for col in connection.introspection.get_table_description(cursor, table_name)]
        if "scout_bonus_percentage" in columns:
            # Use schema_editor to remove the column (database-agnostic)
            cursor.execute(f"ALTER TABLE {table_name} DROP COLUMN scout_bonus_percentage")


def add_column_back(apps, schema_editor):
    """Add the column back for reverse migration."""
    table_name = "aapayout_lootpool"
    with connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE {table_name} " "ADD COLUMN scout_bonus_percentage DECIMAL(5,2) NOT NULL DEFAULT 10.00"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("aapayout", "0006_lootpool_scout_shares"),
    ]

    operations = [
        migrations.RunPython(remove_column_if_exists, add_column_back),
    ]
