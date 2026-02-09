import uvicorn
import csv
import io
import secrets
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Field, Session, SQLModel, create_engine, select
from pydantic import BaseModel
from typing import List, Optional
import os

# --- AUTH CONFIG ---
ADMIN_USER = "admin"
ADMIN_PASS = "geheim123"  # Hier dein Passwort setzen!
security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    # secrets.compare_digest verhindert Timing-Attacken
    is_correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    is_correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)

    if not (is_correct_user and is_correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsche Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- DB MODELL ---
class InventarEintrag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: str  # UUID um Gruppen zu identifizieren
    timestamp: datetime  # Wann wurde eingereicht
    verantwortlicher: str
    abteilung: str
    geraete_id: str
    gebaeude: str
    raum: str
    archiviert: bool = Field(default=False)


# --- PYDANTIC MODELLE ---
class HeaderData(BaseModel):
    name: str
    abteilung: str


class AssetRow(BaseModel):
    geraete_id: str
    gebaeude: str
    raum: str


class SubmissionPayload(BaseModel):
    header: HeaderData
    assets: List[AssetRow]


# --- SETUP ---
base_path = "/data" if os.path.exists("/data") else "."
db_name = f"{base_path}/inventur.db"
engine = create_engine(f"sqlite:///{db_name}")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


# --- USER ROUTEN ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    gebaeude_liste = ["Rathaus - Marktplatz 2",
                      "Haus zur Münze - Marktplatz 10",
                      "Folzstraße 5",
                      "Prinz-Carl-Anlage 3",
                      "Klosterstraße 23",
                      "Lutherring 31",
                      "Feuerwehr - Kyffhäuserstraße 6",
                      "Ludwigsplatz 5",
                      "Musikschule - Valckenbergstraße 18",
                      "Volkshochschule - Willy-Brand-Ring 11",
                      "Würdtweinstraße 12a",
                      "Schönauer Straße 2",
                      "Kirschgartenweg 58",
                      "Wilhelm-Leuschner-Straße 2",
                      "Tourist Information - Neumarkt 14",
                      "Raschi-Haus - Hintere Judengasse 6",
                      "Andreasstift - Weckerlingplatz 1",
                      "Nibelungenmuseum - Fischerpförtchen 10",
                      "Friedhof - Eckenbergstraße 114",
                      "Hohenstaufenring 2a",
                      "IDB Lager - Johann-Braun-Straße 19",
                      "Internetcafe - Sterngasse 10",
                      "Von-Steuben-Straße 6",
                      "Kindertageseinrichtungen",
                      "Kinder- und Jugendbüros",
                      "Pflege- und Physiotherapieschule/Klinikum",
                      "Festplatz - Rheinstraße 55",
                      "Monsheimer Straße 41",
                      "Ortsverwaltungen",
                      "Schloss Herrnsheim - Herrnsheimer Hauptstraße 1",
                      "Seniorenbegegnungsstätte - Kleine Weide 1",
                      "Tiergarten - Hammelsdamm 101",
                      "Umwelthaus - Hammelsdamm 105",
                      "Stadtteilbüros",
                      "Karl-Hofmann-Schule BBS",
                      "Berufsbildende Schule Wirtschaft",
                      "Geschwister-Scholl-Schule Förderschule",
                      "Dalberg Grundschule",
                      "Diesterweg Grundschule",
                      "Ernst-Ludwig Grundschule",
                      "Karmeliter Grundschule",
                      "Kerschensteiner Grundschule",
                      "Klausenberg Grundschule",
                      "Neusatz Grundschule",
                      "Paternus Grundschule",
                      "Pestalozzi Grundschule",
                      "Rheindürkheim Grundschule",
                      "Staudinger Grundschule",
                      "Westend Grundschule",
                      "Wiesengrundschule",
                      "Wiesoppenheim Grundschule",
                      "Eleonoren Gymnasium",
                      "Gauß Gymnasium",
                      "Rudi-Stephan Gymnasium",
                      "Nelly-Sachs-IGS",
                      "Karmeliter Realschule",
                      "Nibelungen Realschule",
                      "Pfrimmtal Realschule",
                      "Westend Realschule",
                      "Abgang",
                      "IDB - Hafenstraße 4",
                      "Carl-Villinger-Straße 9",
                      "Grabenstraße - Am Schwimmbad",
                      "Mainzer Straße 6.6"]
    return templates.TemplateResponse("index.html", {
        "request": request, "gebaeude_liste": gebaeude_liste
    })


@app.post("/submit-all")
async def submit_all(payload: SubmissionPayload):
    # Eine eindeutige ID für diesen "Submit" Vorgang
    sub_id = str(uuid.uuid4())
    ts = datetime.now()

    with Session(engine) as session:
        count = 0
        for asset in payload.assets:
            if asset.geraete_id.strip():
                neuer_eintrag = InventarEintrag(
                    submission_id=sub_id,
                    timestamp=ts,
                    verantwortlicher=payload.header.name,
                    abteilung=payload.header.abteilung,
                    geraete_id=asset.geraete_id,
                    gebaeude=asset.gebaeude,
                    raum=asset.raum
                )
                session.add(neuer_eintrag)
                count += 1
        session.commit()
    return JSONResponse(content={"message": f"{count} Geräte gespeichert."})


# --- ADMIN ROUTEN ---

# 1. Die Admin-Oberfläche (Geschützt)
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, username: str = Depends(get_current_username)):
    return templates.TemplateResponse("admin.html", {"request": request, "user": username})


# 2. Daten API für das JavaScript im Admin-Panel
@app.get("/admin/data")
async def get_admin_data(username: str = Depends(get_current_username)):
    with Session(engine) as session:
        # Wir holen alle Daten, sortiert nach Datum (neueste zuerst)
        statement = select(InventarEintrag).order_by(InventarEintrag.timestamp.desc())
        results = session.exec(statement).all()
        return results


# 3. CSV Export
@app.get("/admin/export")
async def export_csv(username: str = Depends(get_current_username)):
    with Session(engine) as session:
        statement = select(InventarEintrag).order_by(InventarEintrag.timestamp.desc())
        results = session.exec(statement).all()

    # CSV im Speicher erstellen
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # Header
    writer.writerow(
        ["ID", "Timestamp", "Submission-ID", "Verantwortlicher", "Abteilung", "Geräte-ID", "Gebäude", "Raum"])

    # Daten
    for row in results:
        writer.writerow([
            row.id, row.timestamp, row.submission_id,
            row.verantwortlicher, row.abteilung,
            row.geraete_id, row.gebaeude, row.raum
        ])

    output.seek(0)

    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=inventur_export.csv"
    return response


@app.post("/admin/toggle-archive/{item_id}")
async def toggle_archive(item_id: int, username: str = Depends(get_current_username)):
    with Session(engine) as session:
        item = session.get(InventarEintrag, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Status umkehren (True -> False, False -> True)
        item.archiviert = not item.archiviert
        session.add(item)
        session.commit()

        status_text = "archiviert" if item.archiviert else "wiederhergestellt"
        return {"message": f"Eintrag {item.geraete_id} wurde {status_text}."}


@app.post("/admin/toggle-submission/{sub_id}")
async def toggle_submission_group(sub_id: str, username: str = Depends(get_current_username)):
    with Session(engine) as session:
        # Alle Items dieser Submission holen
        statement = select(InventarEintrag).where(InventarEintrag.submission_id == sub_id)
        items = session.exec(statement).all()

        if not items:
            raise HTTPException(status_code=404, detail="Submission not found")

        # Logik: Sind ALLE bereits archiviert?
        all_archived = all(item.archiviert for item in items)

        # Wenn alle archiviert sind -> Wiederherstellen (False)
        # Wenn manche oder keine archiviert sind -> Alle Archivieren (True)
        new_state = not all_archived

        for item in items:
            item.archiviert = new_state

        session.commit()

        action = "wiederhergestellt" if not new_state else "archiviert"
        return {"message": f"Komplette Einreichung ({len(items)} Items) wurde {action}."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)