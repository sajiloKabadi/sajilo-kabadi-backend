from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(first_name="").exclude(full_name=""):
        words = user.full_name.split()
        if words:
            user.first_name = words[0][:24]
            user.save(update_fields=["first_name"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_api_v2")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
