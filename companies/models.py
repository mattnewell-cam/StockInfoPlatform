from logging import lastResort

from django.db import models
from django.conf import settings
from companies.utils import end_of_month

class Company(models.Model):
    name = models.CharField(max_length=255, blank=True, default="")
    exchange = models.CharField(max_length=50, blank=True, default="")
    ticker = models.CharField(max_length=50, blank=True, default="")
    currency = models.CharField(max_length=3, blank=True, default="")
    FYE_month = models.PositiveSmallIntegerField(null=True, blank=True)
    sector = models.CharField(max_length=100, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="")

    description = models.TextField(blank=True, default="")
    special_sits = models.TextField(blank=True, default="")
    writeups = models.JSONField(blank=True, default=list)
    history = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ticker", "exchange"],
                name="uniq_ticker_exchange"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ticker} {self.name}".strip()

    def pass_annual_financials(self, financials_dict, fye_month=None):
        """
        :param financials_dict: {'IS': [['', '2015', '2016', ...], ['Revenue', '43.1', '45.6', ...], ...], 'BS': ...}
        """
        self.FYE_month = self.FYE_month or fye_month
        print(self.FYE_month)
        assert self.FYE_month

        # Ugly bodge: tell if TTM is HY or FY by comparing sales & NI to prior period
        ttm_is_fy = (financials_dict["IS"][1][-1] == financials_dict["IS"][1][-2] and
                     financials_dict["CF"][1][-1] == financials_dict["CF"][1][-2])

        entries = []
        for statement, data in financials_dict.items():
            years = data[0]
            for line in data[1:]:
                metric = line[0]
                for year_index, value in enumerate(line[1:]):

                    year = years[year_index + 1]  # Because enumerate starts at 0 but we're going from line[1]

                    # Continuation of ugly bodge
                    if year == "TTM":
                        if ttm_is_fy:  # Avoid duplicate entry
                            continue
                        else:
                            year = int(years[-2])
                            if self.FYE_month > 6:
                                year += 1
                                month = self.FYE_month - 6
                            else:
                                month = self.FYE_month + 6
                            period_end_date = end_of_month(year, month)
                    else:
                        period_end_date = end_of_month(int(year), self.FYE_month)

                    value = float(value.replace(",", "").replace("-", "0").replace("£", ""))
                    entries.append(Financial(
                        company=self,
                        period_end_date=period_end_date,
                        statement=statement,
                        metric=metric,
                        value=value,
                        currency=self.currency
                    ))
                    # try:
                    #     Financial.objects.update_or_create(
                    #         company=self,
                    #         period_end_date=period_end_date,
                    #         statement=statement,
                    #         metric=metric,
                    #         defaults={
                    #             "value": value,
                    #             "currency": self.currency
                    #         }
                    #     )
                    #     print(f"Successfully created {period_end_date} {metric} for {self.ticker}")
                    # except Exception as e:
                    #     print(e)


        Financial.objects.bulk_create(entries, ignore_conflicts=True)


class Follow(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follows")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="followers")
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="uniq_user_company_follow")
        ]
        # Optimisation
        indexes = [
            models.Index(fields=["user", "followed_at"]),
            models.Index(fields=["company", "followed_at"])
        ]

    def __str__(self) -> str:
        return f"{self.user.name} -> {self.company.ticker} ({self.company.name})"


class Filing(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="filings")
    filing_type = models.CharField(max_length=50)
    filing_date = models.DateField()
    source_url = models.URLField(max_length=1000, blank=True, default="")
    raw_text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "filing_date"]),
            models.Index(fields=["company", "filing_date", "filing_type"])
        ]

    def __str__(self) -> str:
        return f"{self.company.name}: {self.filing_type} ({self.filing_date})"


class Financial(models.Model):
    STATEMENT_CHOICES = {
        "IS": "Income Statement",
        "BS": "Balance Sheet",
        "CF": "Cash Flow",
    }

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="financials")
    period_end_date = models.DateField()
    statement = models.CharField(max_length=2, choices=STATEMENT_CHOICES)
    metric = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=20, decimal_places=6)
    currency = models.CharField(max_length=3, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "period_end_date", "statement", "metric"],
                name="uniq_company_period_statement_metric"
            )
        ]

        indexes = [
            models.Index(fields=["company", "period_end_date"]),
            models.Index(fields=["company", "statement", "metric"])
        ]

    def __str__(self) -> str:
        return f"{self.company.ticker} {self.period_end_date} {self.metric} {self.value}"
