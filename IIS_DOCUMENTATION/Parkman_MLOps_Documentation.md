# ParkMan - MLOps Pipeline (Phase 5)

**Autori:** Benjamin Jakupović i Damjan Đekić

**Kontekst:** Projekt iz kolegija *Inteligentni informacijski sutavi*

**Ak. god.:** 2025./2026.

**Verzija dokumentacije:** v1

## Sadržaj

- [1. Uvod](#1-uvod)
  - [1.1 ParkMan sustav](#11-parkman-sustav)
  - [1.2. Svrha dokumenta](#12-svrha-dokumenta)
  - [1.3. Nadogradnja](#13-nadogradnja)
  - [1.4. Povezana dokumentacija](#14-povezana-dokumentacija)
- [2. Pregled MLOps arhitekture](#2-pregled-mlops-arhitekture)
  - [2.1. High level arhitektura](#21-high-level-arhitektura)
  - [2.2. Event & data flow](#22-event--data-flow)
- [3. Image Fetcher - vremenski kontroliran ingestion](#3-image-fetcher---vremenski-kontroliran-ingestion)
  - [3.1. Uloga Image Fetcher-a u MLOps pipeline-u](#31-uloga-image-fetcher-a-u-mlops-pipeline-u)
  - [3.2. Odgovornosti i granice servisa](#32-odgovornosti-i-granice-servisa)
  - [3.3. Konfiguracija (environment varijable)](#33-konfiguracija-environment-varijable)
  - [3.4. Startup: resolve parking_lot_id iz MongoDB](#34-startup-resolve-parking_lot_id-iz-mongodb)
  - [3.5. Parsiranje timestamp-a iz S3 key-a](#35-parsiranje-timestamp-a-iz-s3-key-a)
  - [3.6. Redis state: last_ts i last_key](#36-redis-state-last_ts-i-last_key)
  - [3.7. Odabir sljedeće slike](#37-odabir-sljedeće-slike)
  - [3.8. Kafka poruka](#38-kafka-poruka)
  - [3.9. Scheduler](#39-scheduler)
- [4. Image Processor - prostorna normalizacija input-a](#4-image-processor---prostorna-normalizacija-input-a)
  - [4.1. Uloga Image Processor u MLOps pipeline-u](#41-uloga-image-processor-u-mlops-pipeline-u)
  - [4.2. Problem koji Image Processor rješava](#42-problem-koji-image-processor-rješava)
  - [4.3. Strategija izdvajanja ROI-ja](#43-strategija-izdvajanja-roi-ja)
  - [4.4. Dohvat slike iz MinIO-a](#44-dohvat-slike-iz-minio-a)
  - [4.5. Izračun ROI-ja i rezanje slike](#45-izračun-roi-ja-i-rezanje-slike)
  - [4.6. Pohrana originalne i procesirane slike](#46-pohrana-originalne-i-procesirane-slike)
  - [4.7. Prosljeđivanje slike YOLO inferenciji](#47-prosljeđivanje-slike-yolo-inferenciji)
  - [4.8. Konfiguracija Image Processor-a](#48-konfiguracija-image-processor-a)
- [5. YOLO Inference servis (lokalni server)](#5-yolo-inference-servis-lokalni-server)
  - [5.1. Razlozi za lokalni YOLO server](#51-razlozi-za-lokalni-yolo-server)
  - [5.2. API YOLO servera](#52-api-yolo-servera)
  - [5.3. Integracija s Car Counter servisom](#53-integracija-s-car-counter-servisom)
- [6. MLflow integracija](#6-mlflow-integracija)
  - [6.1. Uloga MLflow-a u sustavu](#61-uloga-mlflow-a-u-sustavu)
  - [6.2. Dohvat produkcijskog modela](#62-dohvat-produkcijskog-modela)
  - [6.3. Odvajanje treniranja od inferencije](#63-odvajanje-treniranja-od-inferencije)
- [7. YOLO model](#7-yolo-model)
- [8. Batch processing i ClickHouseDB](#8-batch-processing-i-clickhousedb)
  - [8.1. Razlozi za batch obradu](#81-razlozi-za-batch-obradu)
  - [8.2. Nova ClickHouse baza](#82-nova-clickhouse-baza)
  - [8.3. Tjedna average distribucija](#83-tjedna-average-distribucija)
- [9. Dataset management i kontrolirani fault injection](#9-dataset-management-i-kontrolirani-fault-injection)
  - [9.1. Kreiranje novog dataset-a](#91-kreiranje-novog-dataset-a)
  - [9.2. Motivacija za uvođenje Bad Image Injector-a](#92-motivacija-za-uvođenje-bad-image-injector-a)
  - [9.3. Uloga Bad Image Injector-a u arhitekturi](#93-uloga-bad-image-injector-a-u-arhitekturi)
  - [9.4. Način rada](#94-način-rada)
  - [9.5. Odabir ciljanog timestamp-a](#95-odabir-ciljanog-timestamp-a)
  - [9.6. Implementacija: injekcija slike u MinIO](#96-implementacija-injekcija-slike-u-minio)
  - [9.7. Tipovi simuliranih anomalija](#97-tipovi-simuliranih-anomalija)
  - [9.8. Uloga Bad Image Injector-a u batch analizi](#98-uloga-bad-image-injector-a-u-batch-analizi)
- [10. State management i konzistentnost](#10-state-management-i-konzistentnost)
  - [10.1. Motivacija za uvođenje state management-a](#101-motivacija-za-uvođenje-state-management-a)
  - [10.2. Redis kao centralni state store](#102-redis-kao-centralni-state-store)
  - [10.3. Ključevi stanja u sustavu](#103-ključevi-stanja-u-sustavu)
  - [10.4. Korištenje state-a u Image Fetcher-u](#104-korištenje-state-a-u-image-fetcher-u)
  - [10.5. Konzistentnost kroz ponovna pokretanja i padove servisa](#105-konzistentnost-kroz-ponovna-pokretanja-i-padove-servisa)
  - [10.6. Interakcija state-a s Bad Image Injector-om](#106-interakcija-state-a-s-bad-image-injector-om)
- [11. Ogranočenja i poznati trade-off-ovi](#11-ogranočenja-i-poznati-trade-off-ovi)
- [12. Mogući budući razvoj](#12-mogući-budući-razvoj)
- [13. Zaključak](#13-zaključak)

## 1. Uvod

### 1.1 ParkMan sustav
ParkMan je aplikacija koja se sastoji od tri dijela: web aplikacije za 
upravitelje parkiranja, mobilne aplikacije za korisnike i API-ja za senzore. 

Cilj je bio 
stvoriti aplikaciju koja će:

- Omogućiti upraviteljima parkiranja kreiranje novih parkirnih mjesta unutar 
pripadajućih parkirališta
- Omogućiti korisnicima kreiranje računa, traženje slobodnih parkirnih mjesta, kao i 
rezervaciju i plaćanje korištenih mjesta
- Koristiti računalni vid za određivanje količine slobodnih mjesta temeljem 
zauzetosti parkingih mjesta



### 1.2. Svrha dokumenta

U ovom dokumentu se prikazuje tehnička dokumentacija nadogradnje sustava Parkman.

### 1.3. Nadogradnja

U ovoj nadogradnji sustava ParkMan, cilj je bio proširiti postojeće funkcionalnosti sustava dodavanjem:
- sustava za verzioniranje modela (MLFlow), što olakšava postupak praćenja eksperimenata i postavljanje modela računalnog vida.
- praćenja prosječne distribucije korištenosti parkinga kroz vrijeme, kako bi se osiguralo pravovremeno upozoravanje vlasnika na nedosljednosti u zauzetosti parkinga.

### 1.4. Povezana dokumentacija
Na sljedećoj poveznici je detaljnija dokumentacija projekta ParkMan:
    - [Onedrive](https://uniri-my.sharepoint.com/:b:/g/personal/benjamin_jakupovic_uniri_hr1/IQBxKCiG_vY7TqhrMb42BgwBATg140KsFKUupPaZixg55SY?e=DsJmTs)

## 2. Pregled MLOps arhitekture

Ovo poglavlje opisuje MLOps arhitekturu uvedenu u fazi 5 projekta ParkMan, s fokusom na infrastrukturu, tok podataka i integraciju strojnog učenja u produkcijski pipeline. Arhitektura je dizajnirana kao event-driven mikroservisni sustav, u kojem se pomoću message brokera prosljeđuju podaci (slike) modelu (serviranom i verzioniranom pomoću mlflow-a), koji izvršava inferenciju te se sa batch procesima osigurava spremanje rezultata inferencije za daljnju analitiku.

### 2.1. High level arhitektura
![IIS_diagram](IIS_diagram.drawio.png)


Na visokoj razini, MLOps arhitektura sastoji se od sljedećih glavnih komponenti:
1. **Image Fetcher**
    - Servis zadužen za vremenski kontroliran dohvat slika iz dataseta (jedna slika po satu u stvarnom svijetu, odnosno jedna slika na dvije sekunde prilikom testiranja), uz osiguravanje konzistentnog redoslijeda obrade (sekventno po vremenu). Ovaj servis simulira kameru na parkingu koja svakih sat vremena prosljeđuje sliku modelu kako bi za taj parking se odredio broj parkiranih vozila 
2. **Image Processor**
    - Provodi prostornu normalizaciju ulaznih slika (izrezivanje parking zone) kako bi se YOLO modelu isporučivao samo relevantan dio slike. Model tu (obrađenu) sliku sprema u **S3 bucket** s dodatnim transformacijama (kreirajući potencijalni, obrađeni dataset za dotreniravanje modela, uz napomenu da transformacije nisu implementirane) i istovremeno prosljeđuje **Car counter-u** sliku za detekciju. Također sprema neobrađenu kopiju slike u sigurni **S3 bucket** za taj parking, kojem jedino vlasnik tog parkinga ima pristup. Taj bucket ima retention policy od 30 dana.
3. **YOLO Inference Server (Car Counter)**
    - Lokalni servis za inferenciju koji prima obrađene slike iz **image processor-a** i vraća broj detektiranih vozila. Servis učitava model sa MLflow registry-a (model koji je označen kao **production**).
    - Ovaj mikroservis je podijeljen na dva dijela:
        - **Car Counter**, servis koji prima slike obrađene slike koje **image processor** proslijedi, poziva api **YOLO Server-a** za inferenciju i dobiva broj vozila za parking. Taj broj vozila se zapisuje u **Redis** bazu, mijenjajući prethodni zapis za taj parking u **Redisu**.
        - **YOLO server** mikroservis koji učitava odgovarajući model s MlFLow-a (označen kao **production**) te izlaže endpoint za inferenciju modela pomoću FastAPI aplikacije.

4. **MLflow Server**
    - Služi kao registar modela i izvor istine za verzije modela korištene u inferenciji. U MLFlow-u su se zapisivali rezultati treniranja modela (metrike tijekom treniranja, parametri modela, konfiguracijske datoteke korištenog skupa podataka, artefakti stvoreni tijekom treniranja modela te konačne težine modela). Trenirani modeli su se registrirali u mlflowu te su se dodale odgovarajue oznake (npr. oznaka **production**), kako bi se mogao definirati model koji će drugi mikroservisi preuzeti.

5. **MinIO (S3 Storage)**
    - Služi kao pohrana za slike s parking kamera te uključuje pohranu "raw" slika (za simulaciju rada parking kamere), pohranu obrađenih slika (npr. Area of interest extraction) koje se prosljeđuju modelu, pohranu obrađenih slika za dotreniravanje modela te pohranu neobrađenih slika parkinga za sigurnosne potrebe.

6. **Redis**
    - Baza podataka za svaki parking sprema trenutno stanje auta na parkingu te timestamp ažuriranja tog unosa, kako bi se mogao pratiti redoslijed slika koje će **Image fetcher** proslijediti modelu iz pohrane za simulaciju rada parking kamere.

7. **ClickHouseDB**
    - Baza podataka koja se koristi za potrebe analitike korištenosti parkinga. (prosjeci distribucija zauzetosti parkinga po danima u tjednu i detekcija odstupanja te praćenje korištenosti parkinga kroz vrijeme)

8. **Prometheus**
    - Servis za praćenje rada sustava (baze, etl servisi) te spremanje varijable koja se koristi za ažuriranje alarma za nedosljednost u distribuciji korištenja parkinga.
9. **Grafana**
    - Servis koji vlasniku parkinga omogućuje praćenje metrika parkinga (korištenost parkinga kroz vrijeme, prosječna distribucija korištenosti te praćenje alarma o nedosljednosti).
10. **ETL servisi**
    - Batch servisi koji su ključni za analitiku:
        - **Parking usage** servis, koji svakih sat vremena (neposredno nakon što model ažurira unos u Redisu), preuzima trenutno stanje za parkinge u Redisu te ih sprema u **ClickhouseDB** radi praćenja povijesti korištenosti tog parkinga
        - **Weekly parking distribution** servis, koji svakih tjedan dana preuzima povijest parkinga iz **ClickhouseDB**, izračunava prosječnu zauzetost parkinga po satu (tijekom svih 7 dana) te sprema novu tjednu distribuciju u **ClickhouseDB**. Ovaj servis također uspoređuje prethodnu prosječnu zauzetost parkinga te temeljem uspredbe distribucija (preko apsolutne razlike, relativne razlike i Z-testa) definira postoji li odstupanje između nove i prethodne distribucije. U slučaju da postoji, postavlja se alarm u **Prometheusu** te se promjena prikazuje u **Grafani**.
11. **Kafka**:
    - Message broker koji se koristi za stremaning slika između **S3 storage-a** i **image processor-a**

Komponente su orkestrirane putem Docker infrastrukture, dok se komunikacija između servisa temelji na jasnoj podjeli odgovornosti i minimalnoj međuzavisnosti.

### 2.2. Event & data flow
MLOps pipeline u fazi 5 slijedi deterministički i ponovljiv tok podataka, prikazan u nastavku:
1. **Vremenski dohvat slike**
    - Image Fetcher simulira kameru koja uzima sliku parkinga, tako da dohvaća sliku iz MinIO Storage-a na temelju timestamp-a (jedna slika po satu), pri čemu koristi Redis kako bi osigurao da se slike ne obrađuju više puta.
2. **Pohrana i prosljeđivanje**
    - Dohvaćena slike ostaje pohranjena u MinIO-u, a metapodaci o slici (ključ, timestamp, parking ID) prosljeđuju se sljedećem servisu (Kafka).
3. **Prostorna normalizacija**
    - Image Processor prima metapodatke iz Kafke, preuzima sliku iz S3 storage-a, izdvaja relevantni dio slike (ROI) koji sadrži parkiralište te:
        - sprema sigurnosnu kopiju originalne slike
        - sprema "obrađenu" kopiju slike za potrebe dotreniranja modela
        - generira procesiranu verziju slike za inferenciju
4. **YOLO inferencija**
    - Procesirana slika šalje se lokalnom YOLO serveru, koji koristi model dohvaćen iz MLflow registry-a za detekciju i prebrojavanje vozila
5. **Spremanje rezultata**
    - Rezultati inferencije (broj vozila po slici) zapisuju se u:
        - Redis (trenutno stanje)
        - ClickHouseDB (za kasniju analizu) pomoću batch servisa
6. **Batch obrada (periodički)**
    - Na tjednoj bazi izračunavaju se agregirane distribucije zauzeća parkirališta, koje se uspoređuju s prethodnim periodima radi detekcija anomalija

## 3. Image Fetcher - vremenski kontroliran ingestion

### 3.1. Uloga Image Fetcher-a u MLOps pipeline-u
Image Fetcher je servis koji periodički (svaki puni sat) dohvaća sljedeću sliku iz MinIO/S3 bucket-a na temelju timestamp-a iz naziva ključa (S3 key). Odabranu slikku ne preuzima lokalno, već šalje metapodatke (key + parking_lot_id) kroz Kafka topic prema sljedećoj komponenti pipeline-a (Image Processor). Osnovna ideja servisa je da, umjesto nasumičnog uzimanja slike kao prije, osigurava deterministički i reproducibilni redoslijed obrade.

### 3.2. Odgovornosti i granice servisa
Image Fetcher izvodi sljedeće radnje:
- Resolve-a `parking_lot_id` iz MongoDB-a (prema imenu parkinga)
- Lista objekte u MinIO bucket-u
- Parsira timestamp iz naziva ključa (regex uz više različitih formata)
- Bira sljedeći ključ (`ts > last_ts`)
- Šalje Kafka poruku: `{image_key, parking_lot_id}`
- Sprema stanje u Redis (`last_ts`, `last_key`)
- Spava do sljedećeg punog sata

### 3.3. Konfiguracija (environment varijable)
Najvažnije varijable okruženja za Image Fetcher su:
**MinIO/S3**
- `MINIO_ENDPOINT` (npr. `http://minio:9901`)
- `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` (pristup MinIO)
- `BUCKET_CAMERA` (bucket s dataset slikama)

**Kafka**
- `KAFKA_BOOTSTRAP` (Kafka URL)
- `TOPIC` (tema na koju se pretplaćuje)

**Redis**
- `REDIS_HOST` (Redis URL)
- `REDIS_PORT`

**MongoDB (parking_lot_id resolve)**
- `MONGO_MANAGER_DATABASE_R_ONLY_URI` (čitanje podataka o parkingu)
- `PARKING_LOT_NAME` (ime parkinga koje se dohvaća)
- `MONGO_LOTS_COLLECTION` (skup parkinga)

**Scheduler**
- `FETCH_INTERVAL_SECONDS`
    - `0` = spavanje do sljedećeg punog sata
    - `>0` = spavanje x broj sekundi

### 3.4. Startup: resolve parking_lot_id iz MongoDB
Na startu servis resolve-a parking_lot_id na temelju imena parkinga. Dizajnirano je na način da radi samo sa jednim parkingom

```python
def resolve_parking_lot_id() -> str:
    if not MONGO_URI:
        raise RuntimeError("Missing MONGO_MANAGER_DATABASE_R_ONLY_URI")

    client = MongoClient(MONGO_URI)
    try:
        db = client.get_default_database()
        col = db[MONGO_LOTS_COLLECTION]

        if PARKING_LOT_NAME_REGEX:
            q = {"name": {"$regex": PARKING_LOT_NAME, "$options": "i"}}
        else:
            q = {"name": PARKING_LOT_NAME}

        doc = col.find_one(q, {"_id": 1, "name": 1})
        if not doc:
            raise RuntimeError(f"Parking lot not found. Query={q}")

        return str(doc["_id"])
    finally:
        client.close()
```

### 3.5. Parsiranje timestamp-a iz S3 key-a
Fetcher pretpostavlja da timestamp postoji u nazivu objekta (ključu). Podržano je više formata preko regex uzorka, npr.:
- `YYYY-MM-DD HH:MM:SS`
- `YYYYMMDDHHMMSS`
- `YYYY/MM/DD/HH/MM/SS`

Parsiranje vraća `datetime` u UTC formatu:
```python
def parse_ts_from_key(key: str) -> Optional[datetime]:
    for pattern in TS_PATTERNS:
        m = pattern.search(key)
        if not m:
            continue
        return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    return None
```

Ako key nema parsabilan timestamp, taj objekt se ignorira i ne ulazi u izbor.

### 3.6. Redis state: last_ts i last_key
Da bi se izbjegla ponovna obrada istih slika, state se drži u Redis-u kroz dva ključa:
- `image_fetcher:last_ts`
- `image_fetcher:last_key`

```python
def get_last_state(r: redis.Redis) -> Tuple[Optional[datetime], Optional[str]]:
    last_ts_raw = r.get(REDIS_KEY_LAST_TS)
    last_key_raw = r.get(REDIS_KEY_LAST_KEY)

def set_last_state(r: redis.Redis, ts: datetime, key: str) -> None:
    r.set(REDIS_KEY_LAST_TS, ts.isoformat())
    r.set(REDIS_KEY_LAST_KEY, key)
```

Deterministički izbor sljedeće slike omogućava `last_ts`, dok se `last_key` koristi za debugging i praćenje zadnje poslanih slika.

### 3.7. Odabir sljedeće slike
Fetcher lista objekte u bucketu (maksimalno do veličine definirane sa `S3_MAX_KEYS_SCAN`, default 5000), parsira timestamp, sortira i bira:
- ako `last_ts` ne postoji uzima se najranija slika
- inače traži prvi `ts > last_ts`
- ako nema novijih i varijable `WRAP_AROUND_TO_START=true`, vraća se natrag na početak

```python
def pick_next_key_by_timestamp(keys: List[str], last_ts: Optional[datetime]) -> Optional[Tuple[str, datetime]]:
    parsed = [(ts, k) for k in keys if (ts := parse_ts_from_key(k)) is not None]
    parsed.sort(key=lambda x: x[0])

    if last_ts is None:
        ts, k = parsed[0]
        return (k, ts)

    for ts, k in parsed:
        if ts > last_ts:
            return (k, ts)

    if WRAP_AROUND_TO_START:
        ts, k = parsed[0]
        return (k, ts)

    return None
```

### 3.8. Kafka poruka
Kada se odabere slika, šalje se poruka na Kafka topic. Payload je minimalan:
```python
payload = {
    "image_key": next_key,
    "parking_lot_id": parking_lot_id,
}
producer.send(KAFKA_TOPIC, value=payload)
producer.flush()
```

### 3.9. Scheduler
Fetcher ima dva režima.

**Produkcijski režim (default)**
- Spava do sljedećeg punog sata
```python
now = datetime.utcnow()
next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
time.sleep((next_hour - now).total_seconds())
```

**Test režim**
- Ako je ``FETCH_INTERVAL_SECONDS > 0, koristi se fiksni sleep u sekundama
```python
if FETCH_INTERVAL_SECONDS > 0:
    time.sleep(FETCH_INTERVAL_SECONDS)
```

## 4. Image Processor - prostorna normalizacija input-a
Image Processor je servis koji se nalazi između Image Fetcher-a i YOLO inferencijskog servisa. Njegova primarna uloga je prostorna normalizacija slika, odnosno izdvajanje samo onog dijela slike koji zaista sadrži parkiralište (ROI - *Region of interest*).

Time se smanjuje šum u ulaznim podacima, povećava konzistentnost inferencije i pojednostavljuje rad YOLO modela.

### 4.1. Uloga Image Processor u MLOps pipeline-u
Image Processor predstavlja klasičan preprocessing korak u MLOps arhitekturi.
- Dohvaća originalnu sliku in MinIO-a (prema `image_key`)
- Izdvaja statički definirani ROI (parkiralište)
- Sprema:
    - originalnu sliku u security bucket
    - procesiranu (izrezanu) sliku u output bucket
- Prosljeđuje procesiranu sliku YOLO inferencijskom servisu

### 4.2. Problem koji Image Processor rješava
Dataset korišten u ovoj fazi projekta ima sljedeća svojstva:
- Kamera je statična
- Parkiralište se uvijek nalazi na donjem desnom dijelu slike
- Ostatak slike sadrži:
    - zgrade
    - cestu
    - nebo
    - šum koji nije relevantan za detekciju vozila na parkiralištu

Ako bi se cijela slika slala u YOLO model:
- povećava se broj lažnih detekcija
- model uči irelevantne obrasce
- inferencija je sporija i nestabilnija

Zbog toga je uveden Image Processor koji garantira da YOLO uvijek dobiva prostorno konzistentan input.

### 4.3. Strategija izdvajanja ROI-ja
U ovoj fazi koristi se statički ROI, definiran u odnosu na dimenzije slike.

ROI je:
- Pozicioniran u donjem desnom kutu slike
- Definiran kao postotak širine i visine slike
- Ne ovisi o detekciji (nema dinamičkog ROI-ja)

Razlozi zašto je korišten statički ROI:
- Kamera je fiksna
- Dataset je konzistentan
- Implementacija je jednostavna i deterministička

### 4.4. Dohvat slike iz MinIO-a
Image Processor prima poruku koja sadrži `image_key`. Na temelju toga dohvaća originalnu sliku iz MinIO bucket-a.
```pyhton
obj = s3.get_object(Bucket=BUCKET_CAMERA, Key=image_key)
image_bytes = obj["Body"].read()
image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
```

Ako slika ne postoji ili se ne može dekodirati:
- Proces se prekida
- Greška se zapisuje
- Slika se ne šalje dalje u pipeline

### 4.5. Izračun ROI-ja i rezanje slike
ROI se računa dinamički iz dimenzija slike, ali s fiksnim omjerima:
```python
h, w, _ = image.shape

x_start = int(w * 0.55)
y_start = int(h * 0.55)

roi = image[y_start:h, x_start:w]
```

Ovim pristupom:
- Gornji lijevi dio slike se odbacuje
- Zadržava se donji desni kvadrant slike
- Crop radi ispravno za različite rezolucije

### 4.6. Pohrana originalne i procesirane slike
Nakon obrade, Image Processor sprema dvije verzije slike

#### 1. Originalna slika (sigurnosna kopija)
- Služi za:
    - sigurnosne potrebe (ako se na primjer snime ključni dokađaji na parkingu vlasnika)
- Sprema se u poseban bucket
```python
s3.put_object(
    Bucket=SECURITY_BUCKET,
    Key=image_key,
    Body=image_bytes,
    ContentType="image/jpeg"
)
```

#### 2. Procesirana slika (ROI)
- Koristi se isključivo za inferenciju
- Manja je
- Sadrži samo relevantne informacije
```python
_, encoded = cv2.imencode(".jpg", roi)
s3.put_object(
    Bucket=PROCESSED_BUCKET,
    Key=image_key,
    Body=encoded.tobytes(),
    ContentType="image/jpeg"
)
```

### 4.7. Prosljeđivanje slike YOLO inferenciji
Nakon uspješne obrade, Image Processor šalje procesiranu sliku YOLO serveru.

Ovim se Image Processor logički odvaja od inferencije, što je važno MLOps načelo.

### 4.8. Konfiguracija Image Processor-a
Najvažnije varijable okoline:
- `BUCKET_CAMERA` (MinIO bucket sa slikama kamere)
- `BUCKET_SECURITY` (Security storage originalnih slika)
- `BUCKET_PROCESSED` (Pohrana procesiranih slika)
- `ROI_X_START_RATIO` (Postotak slike koji se reže vodoravno)
- `ROI_Y_START_RATIO` (Postotak slike koji se reže okomito)

Omjeri ROI-ja mogu se prilagoditi bez promjene koda.

## 5. YOLO Inference servis (lokalni server)

### 5.1. Razlozi za lokalni YOLO server
Odluka da se YOLO inferencija implementira kao zaseban mikroservis (YOLO Server), umjesto da se ugradi izravno u Car Counter servis, donesena je iz nekoliko arhitektonskih razloga:
- **Izolacija ovisnosti** - YOLO modeli i biblioteke za duboko učenje (PyTorch, Ultralytics) su "teške" i imaju specifične sistemske zahtjeve (npr. CUDA drivere). Odvajanjem u zaseban servis, Car Counter ostaje lagan i fokusiran na poslovnu logiku, dok se okruženje za inferenciju može optimizirati zasebno.
- **Verzioniranje:** YOLO server je dizajniran da dinamički preuzima model s MLflow-a. To omogućuje promjenu modela (npr. ažuriranje na noviju verziju ili promjena arhitekture) promjenom konfiguracije u MLflow registry-ju, bez potrebe za ponovnim kompajliranjem ili redeployanjem Car Counter servisa.

### 5.2. API YOLO servera
YOLO Server je implementiran koristeći **FastAPI** okvir te izlaže jednostavan REST API za komunikaciju.

**Endpoint:** `POST /predict`

Ovaj endpoint prihvaća sliku, provodi inferenciju koristeći učitani model i vraća broj detektiranih objekata ciljane klase.

**Ulazni podaci:**
- `file`: Slika u binarnom formatu (multipart/form-data).

**Izlazni podaci (JSON):**
```json
{
    "car_count": 15
}
```

**Logika inferencije:**
Prilikom pokretanja, servis se spaja na **MLflow Tracking Server** i preuzima artefakte modela definiranog varijablama okoline (`MLFLOW_MODEL_NAME` i `MLFLOW_MODEL_TAG`).
```python
# Učitavanje modela s MLflow-a
model_uri = f"models:/{MODEL_NAME}@{MODEL_TAG}"
model = mlflow.pytorch.load_model(model_uri)
```
Tijekom inferencije, rezultati se filtriraju kako bi se prebrojala samo vozila (klasa koja odgovara detektiranim automobilima u korištenom datasetu).

### 5.3. Integracija s Car Counter servisom
Car Counter servis djeluje kao klijent YOLO servera. Komunikacija se odvija sinkrono putem HTTP protokola.

Proces rada:
1.  **Priprema:** Car Counter prima notifikaciju i dohvaća sliku iz S3 bucketa.
2.  **Slanje zahtjeva:** Poziva se funkcija `yolo_remote_count` koja šalje sliku na adresu definiranu u `YOLO_ENDPOINT` varijabli (default: `http://yolo_server:8000/predict`).
3.  **Obrada odgovora:** Servis čeka JSON odgovor s brojem vozila. U slučaju mrežne greške ili timeout-a, vraća se vrijednost `-1`, što signalizira grešku u detekciji.

Ovakav dizajn omogućuje labavu povezanost između logike brojanja i same implementacije detekcije.

## 6. MLflow integracija

### 6.1. Uloga MLflow-a u sustavu
MLflow je korišten kao centralna platforma za upravljanje cjelokupnim životnim ciklusom modela strojnog učenja u ParkMan sustavu. Njegova uloga je trostruka:

1. Služi kao centralizirani repozitorij za praćenje eksperimenata. Tijekom faze treniranja, skripta `train_with_mlflow.py` automatski bilježi sve relevantne informacije za svako pokretanje:
    *   **Parametre:** Hiperparametri kao što su broj epoha (`epochs`), veličina slike (`imgsz`), i tip modela (`MODEL_TYPE`).
    *   **Metrike:** Pokazatelji performansi modela poput mAP-a (mean Average Precision) i vrijednosti funkcije gubitka (loss), koji se bilježe na kraju svake epohe.
    *   **Artefakte:** Bilo koje datoteke generirane tijekom treniranja, uključujući težine modela (`best.pt`), vizualizacije (npr. `confusion_matrix.png`) i konfiguracijske datoteke (`data-visdrone.yaml`).

2. Koristi se kao registar modela, odnosno centralno mjesto za verzioniranje i upravljanje modelima koji su spremni za produkciju. Svaki model registriran pod određenim imenom (npr. `YOLO_ParkMan_visdrone`) može imati više verzija. Verzije se kasnije označuju tagovima (npr. `production`), što omogućuje jasno razdvajanje modela u razvoju, testiranju i produkciji.

3. Koristi se `mlflow.pytorch` modul za spremanje modela u formatu koji je lako učitati u drugim servisima. Kao pozadinska pohrana za sve artefakte (uključujući i same modele) koristi se **MinIO S3 storage**, što osigurava trajnost i skalabilnost.

### 6.2. Dohvat produkcijskog modela
Jedna od glavnih prednosti MLflow integracije je dinamičko dohvaćanje modela u **YOLO Inference servisu**. Servis nije statički povezan s određenom datotekom modela, već dohvaća verziju označenu za produkcijsku upotrebu izravno iz MLflow Model Registry-ja.

Proces je sljedeći:
1.  Prilikom pokretanja, YOLO server čita varijable okoline `MLFLOW_MODEL_NAME` i `MLFLOW_MODEL_TAG`.
2.  Na temelju tih varijabli konstruira se jedinstveni URI za dohvat modela.
3.  Pozivom `mlflow.pytorch.load_model` preuzimaju se artefakti modela s MinIO-a i učitava se model u memoriju.

```python
# YOLOServer/main.py

# Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME", "YOLO_ParkMan_visdrone")
MODEL_TAG = os.getenv("MLFLOW_MODEL_TAG", "best_stability")

def load_model():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    # Construct the model URI for the registry (e.g., models:/YOLO_ParkMan_visdrone@best_stability)
    model_uri = f"models:/{MODEL_NAME}@{MODEL_TAG}"
    return mlflow.pytorch.load_model(model_uri)
```

Ovaj mehanizam omogućuje "hot-swap" modela u produkciji. Promocija nove, bolje verzije modela svodi se na promjenu taga (npr. premještanje taga `best_stability` s verzije 2 na verziju 3) unutar MLflow sučelja, bez potrebe za ponovnim pokretanjem ili izmjenom koda YOLO servisa.

### 6.3. Odvajanje treniranja od inferencije
Proces treniranja modela u potpunosti je odvojen od produkcijskog pipeline-a. Skripta `train_with_mlflow.py` izvršava se u zasebnom okruženju, ručno pokrenuta.

Koraci u skripti za treniranje:
1.  **Pokretanje MLflow run-a:** Svako treniranje se izvodi unutar `mlflow.start_run()` konteksta, čime se osigurava da su svi parametri i metrike vezani za jedinstveni ID pokretanja.
2.  **Logiranje metrika i artefakata:** Tijekom i nakon treniranja, sve relevantne informacije se šalju na MLflow server.
3.  **Registracija modela:** Nakon što je treniranje završeno i model evaluiran, najbolja verzija modela (`best.pt`) se registrira u MLflow Model Registry-ju.

```python
# YOLOModelTraining/train_with_mlflow.py

# ... (nakon završetka treniranja)

# 1. Log the model artifacts to a temporary path
with tempfile.TemporaryDirectory() as tmp_dir:
    local_model_path = os.path.join(tmp_dir, "model_build")
    mlflow.pytorch.save_model(
        pytorch_model=clean_YOLO_model(best_model),
        path=local_model_path,
        pip_requirements=["ultralytics"]
    )
    mlflow.log_artifacts(local_model_path, artifact_path="model")

# 2. Register the model from the logged artifacts
model_uri = f"runs:/{run.info.run_id}/model"
reg_model = mlflow.register_model(model_uri, "YOLO_ParkMan_visdrone")
```

Ovo odvajanje omogućuje slobodno eksperimentiranje s različitim arhitekturama i hiperparametrima bez utjecaja na stabilnost produkcijskog sustava. Tek kada je nova verzija modela temeljito testirana i potvrđena, ona se pomoću taga označava te koristi u produkciji.

## 7. YOLO model

Za potrebe YOLO Servera se treniralo više kombinacija YOLO modela. Koristili su se YOLO11m i YOLO11s modeli.

Prilikom treniranja, koristilo se više različitih kombinacija datasetova:

- visdrone dataset:
    - prilagođeni visdrone dataset na kojem se detektiraju samo vozila
- visdrone + pklot dataset:
    - dataset koji koristi kombinaciju pklot (dataset za detekciju praznih i zauzetih mjesta temeljem parking kamera) i pklot dataseta, prilakođen za detekcju vozila
- romania dataset:
    - vlastiti, ručno napravljen dataset

Trenirano je ukupno 6 YOLO modela te je provedena usporedba točnosti modela nad odgovarajućim test dijelovima dataseta (svaki dataset je imao svoj testni skup, što znači da se rezultati ne mogu usporediti).

Naposlijetku je za produkciju izabran YOLO11 small model koji je pretreniran nad skupom podataka Rumunjske. To je osiguralo izrazito visoku preciznost modela (slike koje Image Fetcher dohvaća su one nad kojima je model trenirao) sa svrhom bolje demonstracije rada sustava za detekciju anomalija.

Metrike tog modela su prikazane ispod:

| Metrika | Vrijednost |
| :--- | :--- |
| Precision (Box) | 0.9497 |
| Recall (Box) | 0.9590 |
| mAP@50 (Box) | 0.9806 |
| mAP@50-95 (Box) | 0.7924 |
| Validation Box Loss | 0.7818 |
| Validation Class Loss | 0.3926 |
| Validation DFL Loss | 0.9714 |
| Train Box Loss | 0.6195 |
| Train Class Loss | 0.3600 |
| Train DFL Loss | 0.9044 |
| Learning Rate | 0.0003 |
| Model Fitness | 0.7894 |



## 8. Batch processing i ClickHouseDB

### 8.1. Razlozi za batch obradu
- tjedne distribucije
- trendovi zauzeća parkinga

### 8.2. Nova ClickHouse baza
Za potrebe analitike i batch obrade podataka, uvedena je **ClickHouse** baza podataka. ClickHouse je odabrana zbog svojih performansi u analitičkim upitima nad velikim količinama podataka (OLAP).

Za trenutnu fazu (prikazanu u ovom projektu), koriste se dvije ključne tablice unutar `parking_db` baze:

#### 1. Tablica `parking_usage`
Ova tablica služi kao "fact table" koja pohranjuje sirove podatke o zauzetosti parkinga kroz vrijeme. Podaci se u ovu tablicu dodaju iz Redisa putem ETL procesa svakih sat vremena.

**Shema tablice:**
- `timestamp` (DateTime): Vrijeme uzorkovanja podatka.
- `owner_id` (String): ID vlasnika parkinga.
- `owner_full_name` (String): Ime i prezime vlasnika.
- `parking_lot_id` (String): Jedinstveni identifikator parkinga.
- `parking_lot_name` (String): Naziv parkinga.
- `parking_spot_number` (Int32): Ukupan kapacitet parkinga.
- `car_count` (Int32): Broj detektiranih vozila.

**Optimizacija:**
Tablica koristi `MergeTree` engine.
- **Particioniranje:** `(owner_id, toYYYYMM(timestamp))` - omogućuje efikasno upravljanje podacima po vlasnicima i mjesecima.
- **Sortiranje:** `(owner_id, parking_lot_id, timestamp)` - optimizira upite koji filtriraju po vlasniku i parkingu te dohvaćaju vremenske serije.

#### 2. Tablica `parking_usage_baseline`
Ova tablica pohranjuje izračunate tjedne distribucije (baseline) zauzetosti za svaki parking. Koristi se za detekciju anomalija usporedbom trenutnog stanja s povijesnim prosjekom.

**Shema tablice:**
- `baseline_id` (String): Jedinstveni ID tjednog izračuna.
- `calculation_date` (Date): Datum kada je prosjek izračunat.
- `parking_lot_id` (String): Referenca na parking.
- `hour_of_day` (UInt8): Sat u danu (0-23) za koji vrijedi statistika.
- `avg_car_count` (Float64): Prosječan broj vozila (aritmetička sredina).
- `std_dev_car_count` (Float64): Standardna devijacija (koristi se za Z-score).
- `max_observed_cars` (Int32): Maksimalni zabilježeni broj vozila (za planiranje kapaciteta).
- `sample_count` (Int32): Broj uzoraka korištenih za izračun.
- `is_active` (UInt8): Zastavica koja označava je li ovo trenutno važeći baseline.

**Optimizacija:**
Tablica koristi `ReplacingMergeTree` engine, što omogućuje ažuriranje zapisa (npr. deaktivaciju starih baseline-ova) zamjenom redaka s istim ključem sortiranja.
- **Sortiranje:** `(parking_lot_id, hour_of_day, calculation_date)`.

### 8.3. Tjedna average distribucija
- dohvat stare distribucije
- računanje nove
- usporedba i spremanje nove
- alert ako postoji odstupanje

## 9. Dataset management i kontrolirani fault injection
U ovoj fazi projekta poseban je naglasak stavljen na upravljanje dataset-om i testiranje ponašanja MLOps pipeline-a u prisutnosti anomalnih ulaznih podataka. U tu svrhu uvedeni su:
- kontrolirano kreiran dataset
- pomoćni servis Bad Image Injector za simulaciju anomalija

Cilj ovog projekta je pokazati da MLOps pipeline nije testiran samo na "idealnim" podacima, već i na namjerno narušenim scenarijima.

### 9.1. Kreiranje novog dataset-a
Za potrebe treniranja i testiranja modela, kao i za simulaciju rada sustava u realnom vremenu, bilo je potrebno prikupiti vlastiti skup podataka. Taj dataset sadrži sekvencijalne slike parkinga u Rumunjskoj, preuzete tijekom razdoblja od 2 tjedna, gdje su se slike prikupljale svakih sat vremena. Dodatno je prikupljeno i tjedan dana slika iz parkinga u Milanu. Te slike su označene te su one činile jednu varijantu skupa podataka nad kojim se trenirao YOLO model. Slike iz grada u Rumunjskoj su se zatim koristile kao sekvencijalni niz slika za jedan konkretan parking u ParkMan sustavu. Time se omogućilo smisleno računanje distribucije parkinga kroz vrijeme. Slike iz Milana su se zatim koristile kao "loše" slike koje se injektirale u dataset kako bi pokvarile distribuciju tijekom testiranja sustava za uvid u anomalije.

Proces prikupljanja podataka automatiziran je pomoću Python skripti (izvršavanih unutar Jupyter Notebook okruženja) koje periodički dohvaćaju slike s javno dostupnih IP kamera.

**Izvori podataka:**
Korištene su javne kamere koje prikazuju parkirališta u različitim gradovima (Milano, lokacija u Rumunjskoj). Odabir kamera vršen je na temelju lakoće pristupa streamu i jasnog pogleda na parkirna mjesta.

**Tehnička implementacija:**
Skripta za prikupljanje podataka (`periodic_image_save.ipynb`) funkcionira na sljedeći način:
1.  **Povezivanje na stream:** Skripta šalje HTTP GET zahtjev na URL kamere. Budući te kamere koriste MJPEG (Motion JPEG) stream, skripta ne preuzima samo jednu statičnu sliku, već otvara stream i čita podatke u blokovima (`chunks`).
2.  **Parsiranje frame-ova:** Unutar binarnog toka podataka, skripta traži početne (`0xFFD8`) i završne (`0xFFD9`) bajtove koji označavaju JPEG sliku. Na taj način se iz kontinuiranog video streama izdvaja jedan validan frame.
3.  **Spremanje i imenovanje:** Izdvojena slika sprema se lokalno u definiranu mapu (`parking_spot_images`). Datoteke se imenuju uz precizan vremenski žig (npr. `parking_spot_2025-01-15_14-30-00.jpg`). Ovo je kasnije ključno za simulaciju "vremenskog protoka" u Image Fetcher servisu.
4.  **Periodičko izvršavanje:** Skripta je konfigurirana da ponavlja ovaj proces u zadanim intervalima (svakih sat vremena), sve dok se ne prikupi željena količina podataka (definirana varijablom `COLLECTING_HOUR_LENGTH`).

Ovaj pristup omogućio je stvaranje dataset-a koji je konzistentan za jedan konkretan parking u ParkMan sustavu.

### 9.2. Motivacija za uvođenje Bad Image Injector-a
U realnim sustavima za nadzor parkirališta, ulazni podaci često odstupaju od očekivanog obrasca. Mogu se pojaviti:
- slike praznog parkirališta u neuobičajeno vrijeme
- slike s ekstremnim brojem vozila
- slike koje ne odgovaraju prostornoj strukturi dataseta
- slike koje narušavaju povijesnu distribuciju zauzeća

Ako se pipeline testira isključivo na "čistom" dataset-u:
- sustav može djelovati stabilno
- batch analiza neće otkriti slabosti
- anomalije se neće manifestirati u metrikama

Zbog tog razloga uveden je Bad Image Injector koji omogućuje kontrolirano i reproducibilno narušavanje dataset-a bez promjene u glavnom pipeline-u.

### 9.3. Uloga Bad Image Injector-a u arhitekturi
Bad Image Injector je pomoćni servis koji:
- ne sudjeluje u redovnom inference toku
- ne komunicira s YOLO servisom
- ne mijenja logiku Image Fetcher-a i Image Processor-a

Njegova zadaća je ubacivanje anomalnih slika u dataset na način koji je u potpunosti transparentan ostatku sustava. Time se ponaša kao generalni izvor grešaka, a ne kao workaround ili debug alat.

### 9.4. Način rada
Bad Image Injector radi u sljedećim koracima:
1. Dohvaća postojeće slike iz MinIO storage-a
2. Odabire ciljani timestamp za injekciju (trenutno vrijeme ili ručno definirano)
3. Priprema anomalne slike
4. Sprema slike u isti bucket s modificiranim key-em
5. Slika postaje dio regularnog ingestion reda

### 9.5. Odabir ciljanog timestamp-a
Bad Image Injector koristi timestamp-based sustav imenovanja kako bi se:
- anomalna slika pojavila točno u željenom trenutku
- osiguralo da Image Fetvher obradi sliku u predviđenom redoslijedu

Primjeri scenarija:
- injekcija anomalije odmah nakon zadnje "normalne" slike
- ubacivanje anomalije usred tjednog intervala
- simulacija naglog skoska u zauzeću parkinga

Ovaj pristup omogućuje preciznu kontrolu nad eksperimentom.

### 9.6. Implementacija: injekcija slike u MinIO
Bad Image Injector direktno komunicira s MinIO/S3 storage-om. Injekcija se svodi na spremanje nove slike s validnik key-em:
```python
s3.put_object(
    Bucket=BUCKET_CAMERA,
    Key=target_key,
    Body=image_bytes,
    ContentType="image/jpeg"
)
```

Budući da se koristi isti bucket i ista naming konvencija:
- Imaga Fetcher automatski prepoznaje slike
- Nema potrebe za dodatnim flagovima ili metapodacima

### 9.7. Tipovi simuliranih anomalija
U ovoj fazi projekta fokus je na jednostavnim, ali efektivnim anomalijama. Budući da se za YOLO servis uvijek pripremaju slike sa istog parkirališta, Bad Image Injector uzima slike sa drugog parkirališta na kojima u potpunosti ili gotovo nema automobila.

Ovakav slučaj dovoljan je za testiranje:
- batch agregacije
- tjednih distribucija
- usporedbe s povijesnim prosjekom

### 9.8. Uloga Bad Image Injector-a u batch analizi
Anomalne slike koje Bad Image Injector ubacuje:
- prolaze kroz cijeli pipeline
- ulaze u ClickHouseDB
- utječu na tjedne distribucije zauzeća

Time se omogućuje:
- provjera osjetiljivosti batch analize
- validacija detekcije odstupanja
- simulacija realnih "incident" scenarija

## 10. State management i konzistentnost
U MLOps pipeline-u koji obrađuje vremenski organizirane podatke, upravljanje stanjem (state management) predstavlja ključni mehanizam za osiguravanje determinističkog ponašanja, konzistentnosti obrade i izbjegavanje dupliciranja podataka.

State management je u ovom projektu centraliziran pomoću Redis baze, koja služi kao lagana, brza i pouzdana komponenta za dijeljenje stanja između iteracija pipeline-a.

### 10.1. Motivacija za uvođenje state management-a
Bez eksplicitnog upravljanja stanjem, MLOps pipeline bi imao sljedeće probleme:
- ponovna obrada istih slika
- nemogućnost nastavka rada nakon restarta servisa
- nekonzistentni redoslijed obrade
- nemogućnost preciznog batch grupiranja po vremenu

S obzirom na to da se ingestion temelji na timestamp-u, stanje sustava mora sadržavati informaciju o tome koja je zadnja slika obrađena.

### 10.2. Redis kao centralni state store
Redis je odabran kao centralni store stanja zbog sljedećih razloga:
- izuzetno brze operacije čitanja i pisanja
- jedostavna integracija s Python servisima
- in-memory priroda (niska latencija)
- mogućnost jednostavnog resetiranja stanja u eksperimentalnom okruženju

Redis se koristi isključivo za state, a ne za pohranu rezultata ili podataka visoke trajnosti.

### 10.3. Ključevi stanja u sustavu
Implementirani su sljedeći ključevi:
- `image_fetcher:last_ts`
    - timestamp zadnje uspješno poslane slike
- `image_fetcher:last_key`
    - S3 key zadnje poslane slike (debug ili audit svrhe)

Ovi ključevi predstavljaju minimalni, ali dovoljan state potreban za determinističko ponašanje pipeline-a.

### 10.4. Korištenje state-a u Image Fetcher-u
Image Fetcher koristi Redis state u svakom ciklusu rada:
1. Čita `last_ts` i `last_key`
2. Lista objekte u MinIO bucket-u
3. Parsira timestamp iz ključeva
4. Bira prvu sliku za koju vrijedi `ts > last_ts`
5. Šalje Kafka poruku
6. Ako je poruka uspješno poslana, ažurira Redis state
```python
last_ts, last_key = get_last_state(redis_client)

next_key, next_ts = pick_next_key_by_timestamp(keys, last_ts)

producer.send(TOPIC, payload)
producer.flush()

set_last_state(redis_client, next_ts, next_key)
```

Ovim redoslijedom osigurava se da:
- state ne ode ispred stvarne obrade
- ne dolazi do preskakanja slika

### 10.5. Konzistentnost kroz ponovna pokretanja i padove servisa
Jedna od važnih prednosti Redis-based state management-a je otpornost na restart servisa.

Scenarij:
- Image Fetcher se zaustavi (crash, redeploy)
- Redis ostaje aktivan
- Nakon ponovnog pokretanja:
    - Fetcher čita `last_ts`
    - nastavlja obradu od sljedeće slike

Na taj način:
- nema potrebe za ručnim intervencijama
- pipeline se ponaša predvidljivo
- izbjegava se ponovna obrada već procesiranih podataka

### 10.6. Interakcija state-a s Bad Image Injector-om
Bad Image Injector namjerno ne koristi Redis state, ali ga indirektno iskorištava:
- injektirana slika dobiva validan timestamp
- Image Fetcher je vidi kao regularnu sljedeću sliku
- Redis state se normalno ažurira nakon obrade animalije

## 11. Ogranočenja i poznati trade-off-ovi
Iako MLOps infrastruktura razvijena u fazi 4 projekta ParkMan zadovoljava ciljeve eksperimentalnog okruženja, sustav ima niz svjesno prihvaćenih ograničenja i dizajnerskih trade-off-ova.

Ovo poglavlje opisuje ta ograničenja, razloge iza njih te implikacije na stabilnost, skalabilnost i budući razvoj sustava.

Popis ograničenja i poznatih trade-off-ova:
- Sustav pretpostavlja statičnu poziciju kamere i konzistentan pogled na parkiralište. ROI u Image Processor-u je fiksno definiran relativno na dimenzije slike, što pojednostavljuje obradu, ali ne tolerira promjene kuta ili pozicije kamere.
- Ingestion se temelji na timestamp-u ugrađenom u naziv S3 ključa. Ovaj pristup omogućuje deterministički redoslijed obrade, ali zahtijeva strogo poštivanje naming konvencije dataset-a.
- Image Fetcher u svakom ciklusu lista ograničen broj objekata iz bucket-a i parsira timestamp za svaki ključ. Rješenje je robusno i jednostavno za razumijevanje, ali ne skalira optimalno na vrlo velike dataset-ove.
- Upravljanje stanjem u Redis-u svodi se na minimalni set ključeva (`last_ts`, `last_key`). Time se postiže jednostavnost i reproducibilnost, uz cijenu izostanka granularnog praćenja statusa obrade po slici
- YOLO inferencija se izvodi putem lokalnog inference servera, bez horizontalnog skaliranja. Ovaj pristup smanjuje latenciju i olakšava debugiranje, ali nije prilagođen visoko-opterećenim produkcijskim scenarijima.
- Batch analiza se izvodi periodično, s fokusom na agregirane metrike poput tjednih distribucija zauzeća. Sustav ne reagira u realnom vremenu na anomalije.
- Bad Image Injector koristi ručno definirane anomalije i ne generira kompleksne sintetičke poremećaje. Injektiranje slike ostaju u dataset-u i zahtijevaju ručno uklanjanje ako više nisu potrebne.
- Nisu napravljene mjerljive usporedbe između performansi različitih treniranih YOLO modela, odnosno YOLO modeli su trenirani na tri različita dataseta sa tri različita test skupa. Ta treniranja su bila korištena samo za demonstracijske svrhe.
- Model koji se koristi u sustavu je pretreniran nad datasetom Rumunjske kako bi se lakše demonstrirao sustav detekcije anomalija.

Sva navedena ograničenja predstavljaju svjesne dizajnerske odluke prilagođene eksperimentalnoj prirodi projekta te služe kao jasna polazišta za budući razvoj sustava.

## 12. Mogući budući razvoj
U ovom poglavlju naveden je popis mogućih budućih smjerova razvoja projekta.

1. Dinamički ROI i podrška za više kamera
    - Image Processor bi se mogao proširiti dinamičkim određivanjem ROI-ja (npr. na temelju kalibracije kamere ili početne detekcije), čime bi se omogućila podrška za više parkirališta i promjenjive kutove snimanja
2. Automatski retraining modela
    - Batch analiza i povijesni podaci iz ClickHouseDB-a mogu poslužiti kao okidač za automatsko ponovno treniranje YOLO modela u slučaju promjene distribucije podataka
3. Detekcija data i concept drift-a
    - Uvođenje statističkih testova ili modela za drift detection moguće je rano otkriti promjene u ponašanju sustava (npr. sezonalnost ili promjene navika parkiranja)
4. Skaliranje inferencije
    - YOLO inference servis može se prilagoditi horizontalnom skaliranju (npr. više instanci servisa) kako bi sustav mogao podnijeti veći broj ulaznih slika
5. Napredniji fault injection
    - Bad Image Injector može se proširiti generiranjem sintetičkih anomalija (blue, noise, occlusion) kako bi se testirala robusnost modela na realnije poremećaje
6. Kubernetes orkestracija
    - Migracija s Docker Compose okruženja na Kubernetes omogućila bi bolju skalabilnost, upravljanje resusrsima i visoku dostupnost sustava

## 13. Zaključak
U fazi 5 projekta ParMan razvijena je funkcionalna MLOps infrastruktura koja nadograđuje postojeći sustav za detekciju vozila kontroliranim ingestionom podataka, prostornom normalizacijom ulaznih slika i odvojenom inferencijom i batch analizom.

Korištenjem vremenski organiziranog dataset-a, Redis-based state management-a i MLflow registry-ja postignuta je deterministička i reproducibilna obrada podataka, što je temelj svakog ozbiljnog MLOps sustava.

Uvođenje Image Processora i Bad Image Injecotr-a omogućilo je stabilniji rad modela te testiranje ponašanja sustava izvan idealnih scenarije, čime je pipeline validiran i na anomalnim podacima.

Iako sustav ima svjesno prihvaćena ograničenja, ona proizlaze iz eksperimentalne prirode projekta te predstavljaju jasne smjernice za budući razvoj.

Ova faza projekta pokazuje kako se računalni vid može integrirati u širi MLOps kontekst, prelazeći s izolirane model-inferencije prema cjelovitom, skalabilnom i proširivom sustavu
