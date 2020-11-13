import xml.etree.ElementTree as ET
import csv
import gzip
import datetime
from decimal import Decimal
from fractions import Fraction

with open("mwrr/categories.txt", "r") as f:
  cats = dict(x[:-1].rsplit(" ", 1) for x in f.readlines() if x != "\n")
with open("mwrr/markets.txt", "r") as f:
  mkts = dict(x[:-1].rsplit(" ", 1) for x in f.readlines() if x != "\n")

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

# Investments I would not do according to my current strategy
with open("mwrr/mistakes.txt") as f:
  mistakes = set(x.strip() for x in f.readlines())
#mistakes = set([])

currencylist = set(["USD","SEK","NOK","DKK","EUR","GBP","CAD"])
currencies = {"EUR": (Fraction(1), datetime.date.today())}
currenciesall = {"EUR": [(Fraction(1), datetime.date.today())],
                 "USD": [],
                 "NOK": [],
                 "SEK": [],
                 "GBP": [],
                 "CAD": [],
                 "DKK": []}
incomeaccounts = {}
mostrecent = {}
mostrecenteur = {}
ticker_by_id = {}
id_by_ticker = {}
transactions = []
quantities_by_ticker = {}

values = []

inout = {}
inoutnonmistaken = {}

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
  #print k + " " + str(Decimal(v.numerator) / Decimal(v.denominator))
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
  #print ticker + ": " + accid
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
      #print "income " + str(date) + " " + str(quantitytext)
      income += Fraction(quantitytext)*nearest_quote(incomeaccounts[acctext],date)
    if acctext in checkingaccounts:
      currency = checkingaccounts[acctext]
      #print "QUOTE: " + str(nearest_quote(currency,date))
      #value += Fraction(valuetext)*nearest_quote(currency,date)
      value += Fraction(quantitytext)*nearest_quote(currency,date)
    if acctext in ticker_by_id and actiontext in set(["Buy","Sell"]):
      found = True
      quantity += Fraction(quantitytext)
      ticker = ticker_by_id[acctext]
      if ticker not in quantities_by_ticker:
        quantities_by_ticker[ticker] = Fraction(0)
      quantities_by_ticker[ticker] += Fraction(quantitytext)
    elif acctext in ticker_by_id and actiontext not in set(["Buy","Sell"]):
      if not found:
        income_ticker = ticker_by_id[acctext]
  if income != Fraction(0):
    assert income_ticker
    if income_ticker in mistakes:
      mistake = True
      #continue
    if date not in inout:
      inout[date] = Fraction(0)
    inout[date] -= income
    if not mistake:
      if date not in inoutnonmistaken:
        inoutnonmistaken[date] = Fraction(0)
      inoutnonmistaken[date] -= income
    continue
  if found and (ticker in mistakes):
    mistake = True
    #found = False
  if not found:
    continue
  if date not in inout:
    inout[date] = Fraction(0)
  inout[date] += value
  if not mistake:
    if date not in inoutnonmistaken:
      inoutnonmistaken[date] = Fraction(0)
    inoutnonmistaken[date] += value
  if value < 0:
    if ticker not in moneyin_by_id:
      moneyin_by_id[ticker] = Fraction(0)
    moneyin_by_id[ticker] -= value
    if not mistake:
      if ticker not in moneyin_by_id_nonmistaken:
        moneyin_by_id_nonmistaken[ticker] = Fraction(0)
      moneyin_by_id_nonmistaken[ticker] -= value
  else:
    if ticker not in moneyout_by_id:
      moneyout_by_id[ticker] = Fraction(0)
    moneyout_by_id[ticker] += value
    if not mistake:
      if ticker not in moneyout_by_id_nonmistaken:
        moneyout_by_id_nonmistaken[ticker] = Fraction(0)
      moneyout_by_id_nonmistaken[ticker] += value
  #print "TX: " + str(date) + " " + ticker + " val " + str(value) + " " + currency + " @ " + str(quantity)
#print "-----"
#for k,v in sorted(inout.items(), key=lambda x:x[0]):
#  print str(k) + ": " + str(Decimal(v.numerator)/Decimal(v.denominator))
#print "====="
totals = Fraction(0)
for ticker,amnt in quantities_by_ticker.items():
  if amnt == 0:
    continue
  assert ticker not in mistakes
  totval = mostrecenteur[ticker]*amnt
  totals += totval

inoutidx = dict(inout)
inoutidx_nonmistaken = dict(inoutnonmistaken)

# --------------

#fees = 0.995 ** (1/365.25)
fees = 1.0

data = []
with open('vboxshared/index2.csv') as csvfile:
  reader = csv.reader(csvfile, delimiter=';')
  listreader = list(reader)
  try:
    date0 = datetime.datetime.strptime(listreader[1][0].replace(' 0:00',''), "%d.%m.%Y").date()
  except ValueError:
    date0 = datetime.datetime.strptime(listreader[1][0].replace(' 0:00',''), "%d/%m/%Y").date()
  for row in listreader[1:]:
    timestr = row[0].replace(' 0:00','')
    try:
      date = datetime.datetime.strptime(timestr, "%d.%m.%Y").date()
    except ValueError:
      date = datetime.datetime.strptime(timestr, "%d/%m/%Y").date()
    diff = (date-date0).days
    row[2] = row[2].replace(',', '.')
    idxval = Decimal(row[2])
    data += [(date, idxval*Decimal(fees**diff))]

def next_idxquote(date):
  try:
    return sorted([(abs((k-date).days),v) for k,v in data if k >= date], key=lambda x:x[0])[0][1]
  except IndexError:
    return sorted([(abs((k-date).days),v) for k,v in data], key=lambda x:x[0])[0][1]

totalidx = Fraction(0)
for k,v in sorted(inoutidx.items(), key=lambda x:x[0]):
  quote = next_idxquote(k)
  totalidx -= v/Fraction(quote)
totalidx *= Fraction(next_idxquote(datetime.date.today()))

totalidx_nonmistaken = Fraction(0)
for k,v in sorted(inoutidx_nonmistaken.items(), key=lambda x:x[0]):
  quote = next_idxquote(k)
  totalidx_nonmistaken -= v/Fraction(quote)
totalidx_nonmistaken *= Fraction(next_idxquote(datetime.date.today()))

date = datetime.date.today()
if date not in inoutidx:
  inoutidx[date] = Fraction(0)
inoutidx[date] += totalidx

date = datetime.date.today()
if date not in inoutidx_nonmistaken:
  inoutidx_nonmistaken[date] = Fraction(0)
inoutidx_nonmistaken[date] += totalidx_nonmistaken

# Index in and out
for k,v in sorted(inoutidx.items(), key=lambda x:x[0]):
  print str(k) + ": " + str(Decimal(v.numerator)/Decimal(v.denominator))

print
print "=================="
print

# ---------------

date = datetime.date.today()
if date not in inout:
  inout[date] = Fraction(0)
inout[date] += totals

date = datetime.date.today()
if date not in inoutnonmistaken:
  inoutnonmistaken[date] = Fraction(0)
inoutnonmistaken[date] += totals

def npv(dataset,irr):
  total = 0.0
  for k,v in sorted(dataset.items(), key=lambda x:x[0]):
    fv = float(v)
    days = (k-datetime.date.today()).days
    total += fv*(1.0+irr)**(-days/365.0)
  return total
  
# Money in and out
moneyin = 0
moneyout = 0
for k,v in sorted(inout.items(), key=lambda x:x[0]):
  if v < 0:
    moneyin -= v
  else:
    moneyout += v
  print str(k) + ": " + str(Decimal(v.numerator)/Decimal(v.denominator))

#print "Money in " + str(Decimal(moneyin.numerator)/Decimal(moneyin.denominator))
#print "Money out " + str(Decimal(moneyout.numerator)/Decimal(moneyout.denominator))

#print "----"
#for k,v in moneyin_by_id.items():
#  print "Money in " + k + " " + str(Decimal(v.numerator)/Decimal(v.denominator))
#print "----"
#for k,v in moneyout_by_id.items():
#  print "Money out " + k + " " + str(Decimal(v.numerator)/Decimal(v.denominator))
#print "----"

def binsearch(dataset):
  toprange = 100.0
  bottomrange = -0.99
  if npv(dataset, toprange) > 0 or npv(dataset, bottomrange) < 0:
    raise Exception("ERROR")
  for n in range(10000):
    if abs(toprange - bottomrange) < 1e-14:
      break
    mid = (toprange+bottomrange)/2
    if npv(dataset, mid) > 0:
      bottomrange = mid
    else:
      toprange = mid
  return mid

print
print "=================="
print
print "My portfolio", binsearch(inout)
print "My portfolio", npv(inout, 0.0)
print "Index", binsearch(inoutidx)
print "Index", npv(inoutidx, 0.0)
print
print "My portfolio, non-mistaken", binsearch(inoutnonmistaken)
print "My portfolio, non-mistaken", npv(inoutnonmistaken, 0.0)
print "Index, non-mistaken", binsearch(inoutidx_nonmistaken)
print "Index, non-mistaken", npv(inoutidx_nonmistaken, 0.0)

firstdate=sorted(inout.keys())[0]
lastdate=sorted(inout.keys())[-1]
def nearest_indexquote(date):
  return sorted([(idxval,abs((idxdate-date).days)) for idxdate,idxval in data], key=lambda x:x[1])[0][0]
firstquote=nearest_indexquote(firstdate)
lastquote=nearest_indexquote(lastdate)
print
print "First date", str(firstdate), firstquote
print "Last date", str(lastdate), lastquote
print "TWRR", float(lastquote/firstquote)**(365.0/(lastdate-firstdate).days)-1


cat_totals = {}
totals = Fraction(0)
for ticker,amnt in quantities_by_ticker.items():
  if amnt == 0:
    continue
  assert ticker not in mistakes
  totval = mostrecenteur[ticker]*amnt
  if cats[ticker] not in cat_totals:
    cat_totals[cats[ticker]] = Fraction(0)
  cat_totals[cats[ticker]] += totval
  totals += totval

print
for cat, totval in cat_totals.items():
  totval /= totals
  print cat, str(Decimal(100*totval.numerator)/Decimal(totval.denominator))

mkt_totals = {}
mkt_totals_nofortum = {}
totals = Fraction(0)
totals_nofortum = Fraction(0)
for ticker,amnt in quantities_by_ticker.items():
  if amnt == 0:
    continue
  assert ticker not in mistakes
  totval = mostrecenteur[ticker]*amnt
  if mkts[ticker] not in mkt_totals:
    mkt_totals[mkts[ticker]] = Fraction(0)
    mkt_totals_nofortum[mkts[ticker]] = Fraction(0)
  mkt_totals[mkts[ticker]] += totval
  totals += totval
  if ticker != "FORTUM":
    mkt_totals_nofortum[mkts[ticker]] += totval
    totals_nofortum += totval

print
for mkt, totval in mkt_totals.items():
  totval /= totals
  print mkt, str(Decimal(100*totval.numerator)/Decimal(totval.denominator))

print
print "W/O Fortum:"
for mkt, totval in mkt_totals_nofortum.items():
  totval /= totals_nofortum
  print mkt, str(Decimal(100*totval.numerator)/Decimal(totval.denominator))
