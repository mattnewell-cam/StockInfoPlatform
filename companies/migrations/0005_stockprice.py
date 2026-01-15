from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0004_company_writeups'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('open', models.DecimalField(decimal_places=4, max_digits=12)),
                ('high', models.DecimalField(decimal_places=4, max_digits=12)),
                ('low', models.DecimalField(decimal_places=4, max_digits=12)),
                ('close', models.DecimalField(decimal_places=4, max_digits=12)),
                ('volume', models.BigIntegerField()),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prices', to='companies.company')),
            ],
            options={
                'ordering': ['date'],
            },
        ),
        migrations.AddConstraint(
            model_name='stockprice',
            constraint=models.UniqueConstraint(fields=('company', 'date'), name='uniq_company_date_price'),
        ),
        migrations.AddIndex(
            model_name='stockprice',
            index=models.Index(fields=['company', 'date'], name='companies_s_company_5e8c5e_idx'),
        ),
    ]
