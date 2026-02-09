import uvicorn
import csv
import io
import secrets
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException, status
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


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


# --- USER ROUTEN ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    gebaeude_liste = ["Rathaus", "Bürgerbüro", "Bauhof", "Feuerwehr", "Schule A", "Schule B", "Verwaltung II"]
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)