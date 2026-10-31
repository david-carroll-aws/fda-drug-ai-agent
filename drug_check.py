from pymongo import MongoClient

col = MongoClient(os.environ["MONGODB_URI"])["druglabels"]["chunks"]

for name in ["ibuprofen", "metformin", "lisinopril", "phenylephrine"]:
    flt = {"drug": {"$regex": name, "$options": "i"}}
    count = col.count_documents(flt)
    names = col.distinct("drug", flt)[:5]
    print(name, "->", count, "chunks; sample drug names:", names)