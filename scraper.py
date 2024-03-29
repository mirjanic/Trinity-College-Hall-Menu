#!/usr/bin/python
#

import datetime
import re
import shutil
import sys
import urllib.request
from io import StringIO

import pymysql
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfpage import PDFPage

url = 'https://www.trin.cam.ac.uk/wp-content/uploads/Hall-Menu-cur.pdf'
pdf_name = 'trin_menu.pdf'
month = dict(Jan=1, Feb=2, Mar=3, Apr=4, May=5, Jun=6, Jul=7, Aug=8, Sep=9, Oct=10, Nov=11, Dec=12)
no_go = "January|February|March|April|May|June|July|August|September|October|November|December|Servery|Dishes|Further"


def download_file():  # From https://stackoverflow.com/a/7244263
    with urllib.request.urlopen(url) as response, open(pdf_name, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)


def extract_text_from_pdf(path):  # Also from stack-overflow
    rsrcmgr = PDFResourceManager()
    retstr = StringIO()
    codec = 'utf-8'
    laparams = LAParams()
    device = TextConverter(rsrcmgr, retstr, codec=codec, laparams=laparams)
    fp = open(path, 'rb')
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    password = ""
    maxpages = 0
    caching = True
    pagenos = set()

    for page in PDFPage.get_pages(fp, pagenos, maxpages=maxpages, password=password, caching=caching,
                                  check_extractable=True):
        interpreter.process_page(page)

    text = retstr.getvalue()

    fp.close()
    device.close()
    retstr.close()
    return text


def parse_text():
    raw = extract_text_from_pdf(pdf_name)

    days = re.split('LUNCH|DINNER', raw)  # Split raw on meals
    days = list(map(lambda s: s.split('\n'), days))  # Split text into lines
    days = [list(filter(lambda s: not (s.isspace() or s == ''), d)) for d in days]  # Remove empty lines

    begin_date = days[0][2]  # Gets first date of the week

    days = [list(filter(lambda s: re.search("\A(\s*(MON|TUE|WED|THU|SAT|SUN|DIS|SOM|FUR))", s) is None, d)) for d in
            days]
    # Remove entries like MONDAY, TUESDAY, DISHES MAY CONTAIN...
    days.pop(0)  # Remove first, empty sublist

    days = [list(map(str.rstrip, d)) for d in days]  # Strip trailing whitespace

    # Use leading whitespace to merge entries
    # Also use ( and ) to merge notes
    for meal in days:
        i = 0
        while i < len(meal):
            if meal[i][0:2].isspace() or (i > 0 and meal[i - 1][0] == '(' and meal[i - 1][-1] != ')'):
                meal[i - 1] += ' ' + meal.pop(i).lstrip()
                i -= 1
            meal[i] = meal[i].lstrip()
            i += 1

    # Add some HTML tags to text
    days = [list(map(lambda s: "<b>" + s + "</b>" if s[0] != '(' and ':' in s else s, d)) for d in days]
    # Safety measures
    days = [list(filter(lambda s: not re.search(no_go, s), d)) for d in days]

    begin_date = begin_date.split()

    # Get first date of the week
    dd = int(begin_date[0][0:-2])
    mm = int(month[begin_date[1][0:3]])
    yy = datetime.datetime.now().year
    if datetime.datetime.now().month == 12 and mm == 1:
        yy -= 1
    if datetime.datetime.now().month == 1 and mm == 12:
        yy += 1

    date = datetime.date(year=yy, month=mm, day=dd)

    # Reformat data
    i = 0
    pretty_days = []
    while 2 * i + 1 < len(days):
        pretty_days.append(dict(Date=date + datetime.timedelta(days=i),
                                Lunch='\n'.join(days[2 * i]),
                                Dinner='\n'.join(days[2 * i + 1])))
        i += 1

    return pretty_days


def update_db(days, host, user, password, dbname):
    db = pymysql.connect(host, user, password, dbname)
    cursor = db.cursor()
    cursor.execute('SELECT date FROM meals ORDER BY date DESC LIMIT 1;')
    newest = cursor.fetchone()
    if newest is not None and newest[0] >= days[0]["Date"]:
        return
    try:
        for entry in days:
            cursor.execute('INSERT INTO meals(date, lunch, dinner) VALUES("' +
                           str(entry["Date"]) + '", "' +
                           entry["Lunch"] + '", "' +
                           entry["Dinner"] + '");')
        db.commit()
    except:
        db.rollback()

    db.close()


if __name__ == '__main__':
    download_file()
    update_db(parse_text(), sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
