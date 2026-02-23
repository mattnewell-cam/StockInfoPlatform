import django.db.models.deletion
from django.db import migrations, models



def _populate_metric_fk(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        return  # Tables are empty on Postgres; data loaded via migrate_sqlite_to_pg.py
    schema_editor.execute(
        "INSERT INTO companies_financialmetric (name) SELECT DISTINCT metric FROM companies_financial"
    )
    schema_editor.execute(
        "UPDATE companies_financial SET metric_fk_id = "
        "(SELECT id FROM companies_financialmetric WHERE name = companies_financial.metric)"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0019_extend_financial_metric_length'),
    ]

    operations = [
        # 1. Create the metric lookup table
        migrations.CreateModel(
            name='FinancialMetric',
            fields=[
                ('id', models.SmallAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),

        # 2. Drop unique constraint (references old metric column)
        migrations.RemoveConstraint(
            model_name='financial',
            name='uniq_company_period_statement_metric',
        ),

        # 3. Add nullable FK column (temporary name to avoid conflict with existing metric VARCHAR)
        migrations.AddField(
            model_name='financial',
            name='metric_fk',
            field=models.ForeignKey(
                'companies.FinancialMetric',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                db_index=False,
            ),
        ),

        # 4. Populate lookup table and set FK values (SQLite only — Postgres is loaded fresh via migration script)
        migrations.RunPython(
            code=_populate_metric_fk,
            reverse_code=migrations.RunPython.noop,
        ),

        # 5. Drop old columns
        migrations.RemoveField(model_name='financial', name='metric'),
        migrations.RemoveField(model_name='financial', name='currency'),

        # 6. Rename metric_fk -> metric (DB column: metric_fk_id -> metric_id)
        migrations.RenameField(
            model_name='financial',
            old_name='metric_fk',
            new_name='metric',
        ),

        # 7. Make non-nullable now that all rows are populated
        migrations.AlterField(
            model_name='financial',
            name='metric',
            field=models.ForeignKey(
                'companies.FinancialMetric',
                on_delete=django.db.models.deletion.CASCADE,
                db_index=False,
            ),
        ),

        # 8. Restore unique constraint
        migrations.AddConstraint(
            model_name='financial',
            constraint=models.UniqueConstraint(
                fields=['company', 'period_end_date', 'statement', 'metric'],
                name='uniq_company_period_statement_metric',
            ),
        ),
    ]
