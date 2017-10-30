from django.db import models
import directory.models as directory_models
import uuid


class Application(models.Model):
    """
    Модель rest приложений для безопасного доступа по ключам
    """
    key = models.UUIDField(default=uuid.uuid4, editable=False, help_text="UUID, генерируется автоматически", db_index=True)
    name = models.CharField(max_length=255, help_text="Название приложения")
    active = models.BooleanField(default=True, help_text="Флаг активности")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Приложение API'
        verbose_name_plural = 'Приложения API'


class RelationFractionASTM(models.Model):
    """
    Модель соответствия фракций из ASTM для LIS
    """
    MULTIPLIERS = ((0, 1), (1, 10), (2, 100), (3, 1000), (4, 1.9), (5, 2.2), (6, 2.5), (7, 0.1), (8, 0.01),)
    astm_field = models.CharField(max_length=127, help_text="ASTM-поле", db_index=True)
    fraction = models.ForeignKey(directory_models.Fractions, help_text="Фракция")
    multiplier = models.IntegerField(choices=MULTIPLIERS, default=0, help_text="Множитель результата")
    default_ref = models.ForeignKey(directory_models.References, help_text="Референс для сохранения через API", default=None, blank=True, null=True)
    full_round = models.BooleanField(default=False, blank=True, help_text="Округлять весь результат?")

    def __str__(self):
        return self.astm_field + " to \"" + self.fraction.research.title + "." + self.fraction.title + "\" x " + str(self.get_multiplier_display())

    class Meta:
        verbose_name = 'Связь ASTM и фракций'
        verbose_name_plural = 'Связи ASTM и фракций'
