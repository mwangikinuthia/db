"""Decompose custom URL.

    URL format (? marks optional parameter):

    {domain}/series/{varname}/{freq}/{?suffix}/{?start}/{?end}/{?finaliser}

    Examples:
        oil/series/BRENT/m/eop/2015/2017/csv
        ru/series/EXPORT_GOODS/m/bln_rub

    Tokens:
        {domain} is reserved, future use: 'all', 'ru', 'oil', 'ru:bank', 'ru:77'

        {varname} is GDP, GOODS_EXPORT, BRENT (capital letters with underscores)

        {freq} is any of:
            a (annual)
            q (quarterly)
            m (monthly)
            w (weekly)
            d (daily)

        {?suffix} may be:

            unit of measurement (unit):
                example: bln_rub, bln_usd, tkm

            rate of change for real variable (rate):
                rog - change to previous period
                yoy - change to year ago
                base - base index

            aggregation command (agg):
                eop - end of period
                avg - average
"""

from datetime import date
from db.api.queries import select_datapoints
from db.api.utils import DatapointParameters
from db.api.views import get_datapoints_response
from db.api.errors import CustomError400

ALLOWED_FREQUENCIES = ('d', 'w', 'm', 'q', 'a')

ALLOWED_REAL_RATES = (
    'rog',
    'yoy',
    'base'
)
ALLOWED_AGGREGATORS = (
    'eop',
    'avg'
)
ALLOWED_FINALISERS = (
    #'info',  # resereved: retrun json with variable and url description
    'csv',   # to implement: return csv (default)
    'json',  # to implement: return list of dictionaries
    #'xlsx'   # resereved: return Excel file
)




class TokenHelper:
    def __init__(self, tokens: list):
        self.tokens = tokens

    def get_dates_dict(self):
        start_year, end_year = self._find_years()
        result = {}
        if start_year:
            result['start_date'] = self._as_date(start_year, month=1, day=1)
        if end_year:
            result['end_date'] = self._as_date(end_year, month=12, day=31)
        else:
            today = date.today()
            result['end_date'] = self._as_date(today.year, today.month, today.day)
        return result

    def fin(self):
        return self._find_one(ALLOWED_FINALISERS)

    def rate(self):
        return self._find_one(ALLOWED_REAL_RATES)

    def agg(self):
        return self._find_one(ALLOWED_AGGREGATORS)

    def _find_years(self):
        """Extract years from *tokens* list. Pops values found away from *tokens*."""
        start, end = None, None
        integers = [x for x in self.tokens if x.isdigit()]
        if len(integers) in (1, 2):
            start = integers[0]
            self._pop(start)
        if len(integers) == 2:
            end = integers[1]
            self._pop(end)
        return start, end

    @staticmethod
    def _as_date(year: str, month: int, day: int):
        """Generate YYYY-MM-DD dates based on components."""
        return date(year=int(year),
                    month=month,
                    day=day).strftime('%Y-%m-%d')

    def _pop(self, value):
        self.tokens.pop(self.tokens.index(value))

    def _find_one(self, allowed_values):
        """Find entries of *allowed_values* into *tokens*.
           Pops values found away from *tokens*.
        """
        values_found = [p for p in allowed_values if p in self.tokens]
        if not values_found:
            return None
        elif len(values_found) == 1:
            x = values_found[0]
            self._pop(x)
            return x
        else:
            raise CustomError400(values_found)


class InnerPath:

    def __init__(self, inner_path: str):
        """Extract parameters from *inner_path* string.

           Args:
              inner_path is a string like 'eop/2015/2017/csv'

           Methods:
              get_dict() returns inner path tokens as dictionary
        """
        # make list of non-empty strings
        tokens = [token.strip() for token in inner_path.split('/') if token]
        helper = TokenHelper(tokens)
        self.dates = helper.get_dates_dict() 
        # finaliser 
        self.fin = helper.fin()
        # transforms
        self.rate = helper.rate()
        self.agg = helper.agg()
        if self.rate and self.agg:
            raise CustomError400("Cannot combine rate and aggregation.")
        # find unit name, if present
        if tokens:
            self.unit = tokens[0]
        else:
            self.unit = self.rate or None
    
    def get_unit(self):
        return self.unit
        
    def get_dates(self):
        return self.dates


class CustomGET:
    """Return response with data in csv format based on 
       mandatory parameters and inner path.
    """
    @staticmethod
    def make_name(varname, unit=None):
        name = varname
        if unit:
            name = f'{name}_{unit}'
        return name
    
    @staticmethod
    def make_freq(freq: str):
        if freq not in ALLOWED_FREQUENCIES:
            raise CustomError400(f'Frequency <{freq}> is not valid')
        return freq

    def __init__(self, domain, varname, freq, inner_path):
        ip = InnerPath(inner_path)
        # frequency
        self.params = dict(freq = self.make_freq(freq))
        # name
        self.params['name'] = self.make_name(varname, ip.get_unit())
        # dates
        dates_dict = ip.get_dates()
        self.params.update(dates_dict)
        
    def get_datapoints(self):
        datapoint_params = DatapointParameters(self.params).get()
        return select_datapoints(**datapoint_params)

    def get_csv_response(self):
        datapoints = self.get_datapoints()
        return get_datapoints_response(datapoints, 'csv')
