"""
Команда инициализации фиксированного набора секций.

Запуск:
    python manage.py init_sections
"""

from django.core.management.base import BaseCommand

from herd.models import Section


class Command(BaseCommand):
    """
    Создает 8 секций: L1-L4 и R1-R4.
    """

    help = "Создать стандартные 8 секций площадки."

    def handle(self, *args, **options):
        mapping = [
            ("LEFT", 1, "L1"),
            ("LEFT", 2, "L2"),
            ("LEFT", 3, "L3"),
            ("LEFT", 4, "L4"),
            ("RIGHT", 1, "R1"),
            ("RIGHT", 2, "R2"),
            ("RIGHT", 3, "R3"),
            ("RIGHT", 4, "R4"),
        ]
        created = 0
        for side, order, name in mapping:
            _, is_created = Section.objects.get_or_create(
                side=side,
                order=order,
                defaults={"name": name, "capacity": 150},
            )
            created += int(is_created)

        self.stdout.write(self.style.SUCCESS(f"Секции готовы. Новых создано: {created}."))
