import os
from minio import Minio
from dotenv import load_dotenv
import sys

def main():
    # --- Određivanje putanja ---
    # Direktorij u kojem se nalazi ova skripta i slike
    current_dir = os.path.dirname(os.path.abspath(__file__))
    local_image_dir_path = current_dir+"/images/"

    # .env datoteka je u korijenskom direktoriju projekta
    env_path_project_root = os.path.join(current_dir, '.env')
    env_path_to_load = None
    if os.path.exists(env_path_project_root):
        env_path_to_load = env_path_project_root
        print(f"Info: .env datoteka pronađena u korijenu projekta: {env_path_to_load}")
       
    else:
        print(f"Greška: .env datoteka nije pronađena ni u '{current_dir}'.")
        print("Molimo osigurajte da .env datoteka postoji i sadrži MinIO konfiguraciju.")
        sys.exit(1)

    load_dotenv(dotenv_path=env_path_to_load)

    # --- MinIO Konfiguracija ---
    # Uklonite http/https iz endpointa za Minio klijent
    minio_endpoint = "localhost:9901" 
    minio_access_key = os.getenv('MINIO_ACCESS_KEY')
    minio_secret_key = os.getenv('MINIO_SECRET_KEY')
    target_bucket_name = "camera-images"

    print("\n--- MinIO Skripta za Prijenos Slika ---")
    print(f"MinIO Endpoint: {minio_endpoint}")
    print(f"Ciljni Bucket: {target_bucket_name}")
    print(f"Lokalni direktorij sa slikama: {local_image_dir_path}") # local_image_dir_path bi trebao biti definiran
    print("---------------------------------------")

    if not all([minio_endpoint, minio_access_key, minio_secret_key]):
        print("Greška: MinIO varijable okruženja (MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY) nisu postavljene.")
        print(f"Molimo provjerite vašu .env datoteku ({env_path_to_load}).")
        sys.exit(1)

    try:
        # Inicijalizacija MinIO klijenta
        # secure=False ako MinIO radi preko HTTP-a
        # secure=True ako MinIO radi preko HTTPS-a
        # Ovdje pretpostavljamo HTTP jer endpoint nema https://
        minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=False # Postavite na True ako vaš MinIO koristi HTTPS
        )

        # Provjera da li bucket postoji i kreiranje ako ne postoji
        found = minio_client.bucket_exists(target_bucket_name)
        if found:
            print(f"Bucket '{target_bucket_name}' je dostupan.")
        else:
            print(f"Bucket '{target_bucket_name}' ne postoji. Pokušavam ga kreirati...")
            minio_client.make_bucket(target_bucket_name)
            print(f"Bucket '{target_bucket_name}' uspješno kreiran.")
    except Exception as e: # Uhvatite specifičnije MinioException ako je potrebno
        print(f"Greška pri spajanju na MinIO ili kreiranju bucketa: {e}")
        sys.exit(1)

    if not os.path.isdir(local_image_dir_path):
        print(f"Greška: Direktorij sa slikama '{local_image_dir_path}' nije pronađen.")
        sys.exit(1)

    print(f"\nZapočinjanje prijenosa slika iz '{local_image_dir_path}' u bucket '{target_bucket_name}'...")
    uploaded_count = 0
    skipped_count = 0

    for filename in os.listdir(local_image_dir_path):
        local_path = os.path.join(local_image_dir_path, filename)
        if os.path.isfile(local_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            s3_object_key = filename  # Koristi samo ime datoteke kao ključ u S3
            try:
                print(f"Prijenos '{local_path}' u '{target_bucket_name}/{s3_object_key}'...")
                # Korištenje fput_object za prijenos datoteke s lokalne putanje
                minio_client.fput_object(
                    target_bucket_name, s3_object_key, local_path
                )
                uploaded_count += 1
            except Exception as e: # Uhvatite specifičnije MinioException
                print(f"Greška pri prijenosu '{local_path}': {e}. Preskačem.")
                skipped_count += 1

    print("\n--- Sažetak Prijenosa ---")
    print(f"Uspješno preneseno: {uploaded_count} datoteka.")
    print(f"Preskočeno/Neuspjelo: {skipped_count} datoteka.")
    print("--- Proces Prijenosa Završen ---")

if __name__ == "__main__":
    main()
                