from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0003_company_uniq_ticker_exchange'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='writeups',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
