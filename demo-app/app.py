#!/usr/bin/env python3
"""Demo app: writes and reads orders in the CIS-hardened MongoDB."""
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError

HERE = os.path.dirname(os.path.abspath(__file__))

client = MongoClient(
    "mongodb://127.0.0.1:27100/?authSource=shop",               # 6.1 port; the user lives in database shop
    username="appshop",                                           # 2.1 login
    password=os.environ["APP_DB_PASSWORD"],                       # never in the code
    tls=True,                                                     # 4.3 TLS required
    tlsCAFile=os.path.join(HERE, "ca.pem"),                       # trust only our CA (checks the server)
    tlsCertificateKeyFile=os.path.join(HERE, "app-shop.pem"),     # the app's own certificate + key
    serverSelectionTimeoutMS=5000,
)

try:
    orders = client.shop.orders
    orders.insert_one({"item": sys.argv[1] if len(sys.argv) > 1 else "keyboard", "at": datetime.now(timezone.utc)})
    print(f"orders in shop: {orders.count_documents({})}")
    for order in orders.find({}, {"_id": 0}).sort("at", -1).limit(3):
        print(" ", order)
except PyMongoError as err:
    sys.exit(f"database error: {err}")