from app import create_app, db

app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()
    from app.seed import ensure_default_admin
    ensure_default_admin()
print("Database reset and reseeded.")