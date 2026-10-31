from pymongo import MongoClient

MONGO_URI = "mongodb+srv://carrolldavidaws_db_user:superMongoDB@fdarag.xy1fbbu.mongodb.net/"
col = MongoClient(MONGO_URI)["druglabels"]["chunks"]

for name in ["ibuprofen", "metformin", "lisinopril", "phenylephrine"]:
    flt = {"drug": {"$regex": name, "$options": "i"}}
    count = col.count_documents(flt)
    names = col.distinct("drug", flt)[:5]
    print(name, "->", count, "chunks; sample drug names:", names)