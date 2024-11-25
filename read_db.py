from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Product  # Update import to use models.py

def init_db():
    # Create engine
    engine = create_engine('sqlite:///scraper.db')
    # Create all tables
    Base.metadata.create_all(engine)
    print("Database initialized and tables created.")

def print_database_contents():
    # Create engine and session
    engine = create_engine('sqlite:///scraper.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Print products
    print("\n=== Products ===")
    products = session.query(Product).all()
    for product in products:
        print(f"\nTitle: {product.title}")
        print(f"URL: {product.url}")
        print(f"Price: {product.price}")
        print(f"Regular Price: {product.regular_price}")
        print(f"On Sale: {bool(product.on_sale)}")
        print(f"Image: {product.image_url}")

    session.close()

if __name__ == "__main__":
    # init_db()  # Initialize database first
    print_database_contents() 