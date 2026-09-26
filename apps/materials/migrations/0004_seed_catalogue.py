"""Launch catalogue: 20 materials with a starting Kathmandu rate.

Ids, names and prices of Copper (1), Zinc (5), Iron & steel (8),
Plastic (PET) (15), Newspaper (17), Cardboard (19) and Glass (20) come from
the API contract. The rest follow its "Copper 900 down to Glass 8" ordering
and must be checked against lib/data/demo/demo_data.dart in the app; edit
them in the admin (add a new rate row) rather than here.

Runs only on an empty catalogue, so it never overwrites real data.
"""

from django.db import migrations
from django.utils import timezone

CATALOGUE = [
    (1, "Copper", "तामा", "Cu", "metal", 900),
    (2, "Brass", "पित्तल", "Br", "metal", 520),
    (3, "Aluminium", "एल्युमिनियम", "Al", "metal", 210),
    (4, "Batteries", "ब्याट्री", "Bat", "other", 180),
    (5, "Zinc", "जस्ता", "Zn", "metal", 175),
    (6, "E-waste", "इ-वेस्ट", "EW", "other", 120),
    (7, "Stainless steel", "स्टेनलेस स्टिल", "SS", "metal", 90),
    (8, "Iron & steel", "फलाम र स्टिल", "Fe", "metal", 48),
    (9, "Tyres", "टायर", "Tyr", "other", 45),
    (10, "Plastic (HDPE)", "प्लास्टिक (HDPE)", "HDPE", "paper_plastic", 42),
    (11, "Tin cans", "टिनका बट्टा", "Tin", "metal", 40),
    (12, "Plastic (PP)", "प्लास्टिक (PP)", "PP", "paper_plastic", 36),
    (13, "Books & copies", "किताब र कापी", "Bk", "paper_plastic", 32),
    (14, "Office paper", "अफिस कागज", "Pap", "paper_plastic", 31),
    (15, "Plastic (PET)", "प्लास्टिक (PET)", "PET", "paper_plastic", 30),
    (16, "Plastic sheet", "प्लास्टिक पाना", "LDPE", "paper_plastic", 25),
    (17, "Newspaper", "पत्रिका", "News", "paper_plastic", 22),
    (18, "Mixed paper", "मिश्रित कागज", "Mix", "paper_plastic", 16),
    (19, "Cardboard", "कार्टुन", "Box", "paper_plastic", 14),
    (20, "Glass", "सिसा", "Gl", "other", 8),
]


def seed(apps, schema_editor):
    Material = apps.get_model("materials", "Material")
    MaterialRate = apps.get_model("materials", "MaterialRate")
    if Material.objects.exists():
        return
    today = timezone.localdate()
    now = timezone.now()
    for pk, name_en, name_ne, abbr, category, price in CATALOGUE:
        Material.objects.create(id=pk, name_en=name_en, name_ne=name_ne, abbr=abbr, category=category)
        MaterialRate.objects.create(
            material_id=pk, city="Kathmandu", price_per_kg=price, effective_date=today, published_at=now
        )


class Migration(migrations.Migration):
    dependencies = [("materials", "0003_api_v2")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
