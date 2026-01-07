import calendar
import datetime as dt

def end_of_month(year:int, month) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, last_day)