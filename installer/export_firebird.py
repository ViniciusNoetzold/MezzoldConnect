# -*- coding: utf-8 -*-
"""
Script de Exportação e Compatibilidade Firebird / ANSI SQL para Mezzold Connect
Gera dump SQL compatível com Firebird, DBeaver, FlameRobin e outros SGBDs.
"""
import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

def export_sqlite_to_firebird_sql(db_path: str, output_sql_path: str):
    if not os.path.exists(db_path):
        print(f"Banco de dados nao encontrado em: {db_path}")
        return False
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Obter todas as tabelas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "/* ===================================================================",
        f"   MEZZOLD CONNECT - EXPORTACAO DE DADOS PARA FIREBIRD / ANSI SQL",
        f"   Data da Exportacao: {timestamp}",
        f"   Origem: {db_path}",
        "   =================================================================== */\n",
        "SET NAMES UTF8;\n"
    ]
    
    type_map = {
        "INTEGER": "INTEGER",
        "TEXT": "VARCHAR(4096)",
        "REAL": "DOUBLE PRECISION",
        "BLOB": "BLOB SUB_TYPE TEXT",
        "": "VARCHAR(255)"
    }
    
    for table in tables:
        lines.append(f"/* -------------------------------------------------------------------")
        lines.append(f"   TABELA: {table}")
        lines.append(f"   ------------------------------------------------------------------- */")
        
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        
        col_defs = []
        pk_cols = []
        for c in cols:
            cid, name, col_type, notnull, dflt, pk = c
            col_type_upper = col_type.upper().strip()
            fb_type = type_map.get(col_type_upper, "VARCHAR(2048)")
            if "INT" in col_type_upper:
                fb_type = "INTEGER"
            elif "CHAR" in col_type_upper or "TEXT" in col_type_upper:
                fb_type = "VARCHAR(4096)"
                
            not_null_str = " NOT NULL" if notnull else ""
            col_defs.append(f"    {name} {fb_type}{not_null_str}")
            if pk:
                pk_cols.append(name)
                
        if pk_cols:
            col_defs.append(f"    CONSTRAINT PK_{table.upper()} PRIMARY KEY ({', '.join(pk_cols)})")
            
        create_stmt = f"CREATE TABLE {table} (\n" + ",\n".join(col_defs) + "\n);\n"
        lines.append(create_stmt)
        
        # Inserir dados
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        col_names = [d[0] for d in cursor.description]
        
        for r in rows:
            vals = []
            for v in r:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    safe_v = str(v).replace("'", "''")
                    vals.append(f"'{safe_v}'")
            ins_stmt = f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({', '.join(vals)});"
            lines.append(ins_stmt)
            
        lines.append("\nCOMMIT;\n")
        
    conn.close()
    
    with open(output_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"Exportacao concluida com sucesso para: {output_sql_path}")
    return True

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "C:\\MezzoldConnect\\data\\mezzold_connect.sqlite3"
    out = sys.argv[2] if len(sys.argv) > 2 else "C:\\MezzoldConnect\\data\\mezzold_connect_firebird.sql"
    export_sqlite_to_firebird_sql(db, out)