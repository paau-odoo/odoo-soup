from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, Text, Double, DateTime, String
from magicprompt import prompt
from utils import condense, listFiles, identifyFiles, config, engine, parseConfig
import utils
from datetime import datetime
import gzip

# Read config file and do some setup
Base = declarative_base()


# Log line model
class Log(Base):
    __tablename__ = config["table"]

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    level = Column(String(15))
    origin = Column(Text)
    type = Column(String(64))
    ip = Column(String(128))
    http = Column(String(10))
    route = Column(Text)
    code = Column(Integer)
    time = Column(Double)
    user = Column(Text)
    model = Column(Text)
    records = Column(Text)
    text = Column(Text)


def checkDate(date: str):
    try:
        format = "%Y-%m-%d %H:%M:%S"
        date = datetime.strptime(date, format)
        return date
    except:
        return None


def applyTrim(str, field, lineType=None):
    # Again, type will have to be done blindly
    if field == "type":
        sS, sE = (
            utils.parse["default"]["type"]["sliceStart"],
            utils.parse["default"]["type"]["sliceEnd"],
        )
    else:
        sS, sE = (
            utils.parse[lineType]["fields"][field]["sliceStart"],
            utils.parse[lineType]["fields"][field]["sliceEnd"],
        )

    # There should always be slice start, be it 0 or something specific
    if sS is None and sE is None:
        return str
    if sE is None:
        return str[sS:]
    return str[sS:sE]


def fromLine(splitLine, field, lineType=None):
    # type needs to be generic determined for any line
    if field == "type":
        raw = splitLine[utils.parse["default"]["type"]["index"]]
        return applyTrim(raw, field)

    f = utils.parse[lineType]["fields"].get(field)
    if f:
        try:
            raw = splitLine[f["index"]]
            return applyTrim(raw, field, lineType)
        except:
            return


def processLine(line: str) -> tuple:
    line = line.strip()

    skeletor = {
        "date": None,
        "level": None,
        "origin": None,
        "ip": None,
        "http": None,
        "route": None,
        "code": None,
        "time": None,
        "user": None,
        "model": None,
        "records": None,
        "text": None,
    }

    # Line should be completely skipped if doesnt start with a date
    date = checkDate(line.split(",")[0])
    if not date:
        return (2, None)

    skeletor["date"] = date

    spl = line.split(" ")

    # Determine line type
    lineType = fromLine(spl, "type")

    if lineType not in set(utils.parse.keys()):
        return (1, lineType)

    # Based on type, assign all the values to the skeleton

    # Based on type, populate the skeleton
    for k in skeletor:
        # Already assigned date
        if k != "date":
            skeletor[k] = fromLine(spl, k, lineType)

    # Add in the type and raw text
    skeletor["type"] = utils.parse[lineType]["alias"]

    skeletor["text"] = " ".join(spl[utils.parse["default"]["type"]["index"] :])
    return (0, skeletor)


def listVersions():
    print("Custom Configs:")
    if len(config["parser"]) > 1:
        for v in config["parser"]:
            if v != "default":
                print(f"  {v}")
    else:
        print("  **None**")


def convertToSql(full_file_path: str):
    # Set up sql conn
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Lines to import
    logLines = []

    skipped = []

    # Read the selected file
    with gzip.open(full_file_path, "rt") as f:
        for line in f:
            status, processed = processLine(line)

            # If processing exits with 1 status, that means the type of the logline was skipped.
            if status == 1:
                skipped.append(processed)
                continue
            if status == 2:
                # 2 is total skip
                continue

            # Add to the loglines if there were no errors
            logLines.append(processed)

        # Print out the lines that were skipped based on TYPE
        skipped = condense(skipped)
        print(
            "The following logline types were present in this log and will be skipped (sorted by frequency):"
        )
        for s in skipped:
            print(f"  {s}")

    print("Creating log line objects...")
    logs = [Log(**l) for l in logLines]
    print("Writing to DB...")
    session.add_all(logs)
    session.commit()


def main():
    print(f"Working in {config['path']}")
    print()
    print("Target:")
    print(f"  {config['db_name']} -> {config['table']}")

    print()
    files = identifyFiles(config["path"])

    if len(files):
        print(f"({len(files)}) logfiles detected:")
        listFiles(files)
        print()
        # Responses will be 1 indexed, so need to subtract 1 for actual file index
        resp = (
            prompt("Select a logfile to convert", numOnly=1, clearAfterResponse=1) - 1
        )

        listVersions()
        vers = prompt(
            "Choose a configuration (Enter for default)",
            notEmpty=False,
            clearAfterResponse=1,
        )

        print(f"Converting {files[resp][0]} to SQL table...")
        utils.parse = parseConfig(vers or "default")
        convertToSql(files[resp][1])

    else:
        raise FileNotFoundError(
            f"No logfiles (xxxx.gz) detected in CWD {config['path']}"
        )


main()
