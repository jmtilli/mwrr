#!/usr/bin/env python3
from __future__ import print_function
from __future__ import division
import xml.etree.ElementTree as ET
import csv
import gzip
import datetime
import getopt
import sys
from decimal import Decimal
from fractions import Fraction

filename = "gnucash/gnucash.gnucash"

checkingaccounts = {
  "f1ec672282d88909c70fe834b90af496": "EUR", # Nordea
  "2bb3fbf1fc77aa7eab4453638afd022d": "NOK",
  "ed9db9c603d9634b943c0e1ef67cb69d": "EUR",
  "17842d5451a5ea9bc67866cef52570a6": "USD",
  "aff014c4e1db58420455d215a99b020f": "SEK",
  "3ad0a9e79aa528a0f21e165400733970": "EUR", # Receivables Sponda
}
dividend_income_account = "722b4e3a7e646163c19dcdaa4276c877"

currencylist = set(["USD","SEK","NOK","DKK","EUR","GBP","CAD","CHF"])
currencies = {"EUR": (Fraction(1), datetime.date.today())}
currenciesall = {"EUR": [(Fraction(1), datetime.date.today())],
                 "USD": [],
                 "NOK": [],
                 "SEK": [],
                 "GBP": [],
                 "CAD": [],
                 "DKK": [],
                 "CHF": []}
incomeaccounts = {}
mostrecent = {}
mostrecenteur = {}
ticker_by_id = {}
id_by_ticker = {}
transactions = []
quantities_by_ticker = {}

values = []

inout = {}

def nearest_quote(currency, date):
  curdata = currenciesall[currency]
  return sorted([(k,abs((v-date).days)) for k,v in curdata], key=lambda x:x[1])[0][0]

with gzip.open(filename, "rb") as f:
  content = f.read()
tree = ET.fromstring(content)
book = tree.find('{http://www.gnucash.org/XML/gnc}book')
pricedb = book.find('{http://www.gnucash.org/XML/gnc}pricedb')
for pricexml in pricedb.iter('price'):
  commodityxml = pricexml.find('{http://www.gnucash.org/XML/price}commodity')
  currencyxml = pricexml.find('{http://www.gnucash.org/XML/price}currency')
  ticker = commodityxml.find('{http://www.gnucash.org/XML/cmdty}id').text
  currency = currencyxml.find('{http://www.gnucash.org/XML/cmdty}id').text
  timexml = pricexml.find('{http://www.gnucash.org/XML/price}time')
  timestr = timexml.find('{http://www.gnucash.org/XML/ts}date').text
  timestr = timestr.replace(' +0300','')
  timestr = timestr.replace(' +0200','')
  timestr = timestr.replace(' +0000','')
  date = datetime.datetime.strptime(timestr, "%Y-%m-%d %H:%M:%S").date()
  value = pricexml.find('{http://www.gnucash.org/XML/price}value').text
  f = Fraction(value)
  p,q = value.split('/')
  d = Decimal(int(p)) / Decimal(int(q))
  if ticker in currencylist and currency == "EUR":
    olddate = None
    if ticker in currencies:
      olddate = currencies[ticker][1]
    if olddate is None or date > olddate:
      currencies[ticker] = (f, date)
      currenciesall[ticker] += [(f, date)]
  elif ticker not in currencylist:
    olddate = None
    if ticker in mostrecent:
      olddate = mostrecent[ticker][2]
    if olddate is None or date > olddate:
      mostrecent[ticker] = (f, currency, date)
for k,v in mostrecent.items():
  f,currency,date = v
  mostrecenteur[k] = f*currencies[currency][0]
for k,v in mostrecenteur.items():
  #print(k + " " + str(Decimal(v.numerator) / Decimal(v.denominator)))
  pass

moneyin_by_id = {}
moneyout_by_id = {}
moneyin_by_id_nonmistaken = {}
moneyout_by_id_nonmistaken = {}

for accxml in book.iter('{http://www.gnucash.org/XML/gnc}account'):
  accid = accxml.find('{http://www.gnucash.org/XML/act}id').text
  acctype = accxml.find('{http://www.gnucash.org/XML/act}type').text
  if acctype == "INCOME":
    accparent = accxml.find('{http://www.gnucash.org/XML/act}parent').text
    if accparent != dividend_income_account:
      continue
    currency = accxml.find('{http://www.gnucash.org/XML/act}commodity').find('{http://www.gnucash.org/XML/cmdty}id').text
    incomeaccounts[accid] = currency
  if acctype != "STOCK" and acctype != "MUTUAL":
    continue
  ticker = accxml.find('{http://www.gnucash.org/XML/act}commodity').find('{http://www.gnucash.org/XML/cmdty}id').text
  ticker_by_id[accid] = ticker
  id_by_ticker[ticker] = accid
  #print(ticker + ": " + accid)
for trnxml in book.iter('{http://www.gnucash.org/XML/gnc}transaction'):
  ticker = None
  mistake = False
  income_ticker = None
  splitsxml = trnxml.find('{http://www.gnucash.org/XML/trn}splits')
  datepostxml = trnxml.find('{http://www.gnucash.org/XML/trn}date-posted')
  timestr = datepostxml.find('{http://www.gnucash.org/XML/ts}date').text
  timestr = timestr.replace(' +0300','')
  timestr = timestr.replace(' +0200','')
  timestr = timestr.replace(' +0000','')
  date = datetime.datetime.strptime(timestr, "%Y-%m-%d %H:%M:%S").date()
  found = False
  value = Fraction(0)
  income = Fraction(0)
  quantity = Fraction(0)
  for splitxml in splitsxml.iter('{http://www.gnucash.org/XML/trn}split'):
    acctext = splitxml.find('{http://www.gnucash.org/XML/split}account').text
    actionxml = splitxml.find('{http://www.gnucash.org/XML/split}action')
    valuetext = splitxml.find('{http://www.gnucash.org/XML/split}value').text
    quantitytext = splitxml.find('{http://www.gnucash.org/XML/split}quantity').text
    actiontext = actionxml is not None and actionxml.text or None
    if acctext in incomeaccounts:
      continue
    if acctext in checkingaccounts:
      currency = checkingaccounts[acctext]
      #print("QUOTE: " + str(nearest_quote(currency,date)))
      #value += Fraction(valuetext)*nearest_quote(currency,date)
      value += Fraction(quantitytext)*nearest_quote(currency,date)
    if acctext in ticker_by_id and actiontext in set(["Buy","Sell","Split"]):
      found = True
      quantity += Fraction(quantitytext)
      ticker = ticker_by_id[acctext]
      if ticker not in quantities_by_ticker:
        quantities_by_ticker[ticker] = Fraction(0)
      quantities_by_ticker[ticker] += Fraction(quantitytext)
    elif acctext in ticker_by_id and actiontext not in set(["Buy","Sell"]):
      if not found:
        income_ticker = ticker_by_id[acctext]
  if not found:
    continue
  if date not in inout:
    inout[date] = []
  inout[date].append("TX: " + str(date) + " " + ticker + (" val %.2f" % (value,)) + " " + currency + " @ %.6f " % (quantity,))
for k,v in sorted(inout.items()):
  for vv in v:
    print(vv)
