"""
CSV to PostgreSQL Import Script
Import existing CSV files to database and delete them
"""
import os
import sys
import json
import csv
import re
import psycopg2
from datetime import datetime

def load_settings():
    with open('settings.json', 'r', encoding='utf8') as f:
        return json.load(f)

def sanitize_table_name(name: str) -> str:
    """Clean table name, keep only letters, numbers and underscore"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)

def connect_db(db_config):
    return psycopg2.connect(
        host=db_config['db_host'],
        port=db_config['db_port'],
        database=db_config['db_name'],
        user=db_config['db_user'],
        password=db_config['db_password']
    )

def create_table(cursor, table_name):
    """Create log table"""
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS "{table_name}" (
        id SERIAL PRIMARY KEY,
        tweet_date TIMESTAMP,
        display_name VARCHAR(255),
        user_name VARCHAR(255),
        tweet_url TEXT,
        media_type VARCHAR(50),
        media_url TEXT,
        saved_filename VARCHAR(500),
        tweet_content TEXT,
        favorite_count INTEGER DEFAULT 0,
        retweet_count INTEGER DEFAULT 0,
        reply_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_sql)

    # Create indexes
    try:
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_tweet_date ON "{table_name}" (tweet_date);')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_media_type ON "{table_name}" (media_type);')
    except:
        pass

def parse_csv_to_records(csv_path):
    """Parse CSV file, return record list"""
    records = []
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        rows = list(reader)

        # Skip first 3 rows (header info)
        for row in rows[3:]:
            if len(row) < 11:
                continue

            try:
                # Parse time
                tweet_date_str = row[0]
                try:
                    tweet_date = datetime.strptime(tweet_date_str, '%Y-%m-%d %H:%M')
                except:
                    try:
                        tweet_date = datetime.strptime(tweet_date_str, '%Y-%m-%d')
                    except:
                        tweet_date = None

                record = {
                    'tweet_date': tweet_date,
                    'display_name': row[1],
                    'user_name': row[2],
                    'tweet_url': row[3],
                    'media_type': row[4],
                    'media_url': row[5],
                    'saved_filename': row[6],
                    'tweet_content': row[7] if len(row) > 7 else '',
                    'favorite_count': int(row[8]) if row[8].isdigit() else 0,
                    'retweet_count': int(row[9]) if row[9].isdigit() else 0,
                    'reply_count': int(row[10]) if len(row) > 10 and row[10].isdigit() else 0,
                }
                records.append(record)
            except Exception as e:
                print(f"  Parse row failed: {row[:3]}... Error: {e}")
                continue

    return records

def import_csv_to_db(conn, table_name, records):
    """Import records to database"""
    cursor = conn.cursor()
    create_table(cursor, table_name)

    insert_sql = f"""
        INSERT INTO "{table_name}" (
            tweet_date, display_name, user_name, tweet_url, media_type,
            media_url, saved_filename, tweet_content, favorite_count,
            retweet_count, reply_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    imported = 0
    for record in records:
        try:
            cursor.execute(insert_sql, (
                record['tweet_date'],
                record['display_name'],
                record['user_name'],
                record['tweet_url'],
                record['media_type'],
                record['media_url'],
                record['saved_filename'],
                record['tweet_content'],
                record['favorite_count'],
                record['retweet_count'],
                record['reply_count']
            ))
            imported += 1
        except Exception as e:
            print(f"  Insert record failed: {e}")

    conn.commit()
    return imported

def main():
    settings = load_settings()
    save_path = settings.get('save_path', 'D:/twitter_download/assets')

    db_config = {
        'db_host': settings.get('db_host', '127.0.0.1'),
        'db_port': settings.get('db_port', 5432),
        'db_name': settings.get('db_name', 'twitter_download'),
        'db_user': settings.get('db_user', 'postgres'),
        'db_password': settings.get('db_password', '123456')
    }

    print("=" * 60)
    print("CSV to PostgreSQL Import Tool")
    print("=" * 60)

    try:
        conn = connect_db(db_config)
        print("[OK] Database connected")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return

    total_csv = 0
    total_imported = 0
    total_deleted = 0

    # Iterate all user folders
    for user_folder in os.listdir(save_path):
        user_path = os.path.join(save_path, user_folder)
        if not os.path.isdir(user_path):
            continue

        # Find CSV files
        csv_files = [f for f in os.listdir(user_path) if f.endswith('.csv')]

        if not csv_files:
            continue

        table_name = sanitize_table_name(user_folder)
        print(f"\nProcessing user: {user_folder}")
        print(f"  Table: {table_name}")

        for csv_file in csv_files:
            csv_path = os.path.join(user_path, csv_file)
            print(f"  Reading: {csv_file}")

            try:
                records = parse_csv_to_records(csv_path)
                print(f"    Parsed {len(records)} records")

                if records:
                    imported = import_csv_to_db(conn, table_name, records)
                    print(f"    Imported {imported} records")
                    total_imported += imported

                    # Delete CSV file
                    os.remove(csv_path)
                    print(f"    Deleted: {csv_file}")
                    total_deleted += 1
                else:
                    print(f"    No valid data, skipping")
                    os.remove(csv_path)
                    print(f"    Deleted empty file: {csv_file}")
                    total_deleted += 1

            except Exception as e:
                print(f"    Processing failed: {e}")

        total_csv += len(csv_files)

    conn.close()

    print("\n" + "=" * 60)
    print("Import completed!")
    print(f"CSV files processed: {total_csv}")
    print(f"Records imported: {total_imported}")
    print(f"CSV files deleted: {total_deleted}")
    print("=" * 60)

if __name__ == '__main__':
    main()
