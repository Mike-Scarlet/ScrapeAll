
import hashlib

J = r"J:\es_scrape"
a = J + "\\312236\\NINOMAE INA NIS - ハート111 (ゆり).funscript"
b = J + "\\312236\\NINOMAE INA NIS - ハート111 (ゆり)\\NINOMAE INA'NIS - ハート111 (ゆり).funscript"
for p in (a, b):
    print(hashlib.md5(open(p, "rb").read()).hexdigest(), p.split("\\")[-1])
