from abc import ABC, abstractmethod
from typing import List, Dict, Any
import os
import json
import logging
from sqlalchemy import Column, Integer, String, Boolean, Table, MetaData
from sqlalchemy.exc import SQLAlchemyError
import logging
from typing import List, Dict, Any

class StorageStrategy(ABC):
    @abstractmethod
    def save_products(self, products: List[Dict[str, Any]]) -> None:
        pass

class JsonFileStorage(StorageStrategy):
    def __init__(self, file_path: str = 'products.json'):
        self.file_path = file_path

    def save_products(self, products: List[Dict[str, Any]]) -> None:
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path) if os.path.dirname(self.file_path) else '.', exist_ok=True)
        
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2)
        logging.info(f"Products saved to {self.file_path}")

class DatabaseStorage(StorageStrategy):
    def __init__(self, session):
        self.session = session
        self.setup_database()

    def setup_database(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        metadata = MetaData()
        
        # Define the products table
        self.products_table = Table(
            'products', metadata,
            Column('id', Integer, primary_key=True),
            Column('title', String(500), nullable=False),
            Column('url', String(500), unique=True, nullable=False),
            Column('price', String(50)),
            Column('regular_price', String(50)),
            Column('image_url', String(500)),
            Column('on_sale', Boolean, default=False)
        )

        # Create the table if it doesn't exist
        try:
            metadata.create_all(self.session.get_bind())
            logging.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logging.error(f"Error creating database tables: {e}")
            raise

    def clean_product_data(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate product data before saving."""
        return {
            'title': str(product.get('product_title', '')),
            'url': str(product.get('product_url', '')),
            'price': str(product.get('product_price', '0.00')),
            'regular_price': str(product.get('regular_price', '0.00')),
            'image_url': str(product.get('path_to_image', '')),
            'on_sale': bool(product.get('on_sale', False))
        }

    def save_products(self, products: List[Dict[str, Any]]) -> int:
        """
        Save products to database, handling both inserts and updates.
        Returns the number of successfully saved products.
        """
        if not products:
            logging.warning("No products to save")
            return 0

        saved_count = 0
        
        for product in products:
            try:
                # Clean and validate the product data
                clean_data = self.clean_product_data(product)
                
                # Skip if required fields are missing
                if not clean_data['url'] or not clean_data['title']:
                    logging.warning(f"Skipping product with missing required fields: {clean_data}")
                    continue

                # Check if product exists
                existing = self.session.execute(
                    self.products_table.select().where(
                        self.products_table.c.url == clean_data['url']
                    )
                ).first()

                if existing:
                    # Update existing product
                    self.session.execute(
                        self.products_table.update()
                        .where(self.products_table.c.url == clean_data['url'])
                        .values(**clean_data)
                    )
                else:
                    # Insert new product
                    self.session.execute(
                        self.products_table.insert().values(**clean_data)
                    )
                
                saved_count += 1

            except SQLAlchemyError as e:
                logging.error(f"Database error for product {clean_data.get('title')}: {str(e)}")
                self.session.rollback()
                continue
            except Exception as e:
                logging.error(f"Unexpected error processing product: {str(e)}")
                continue

        try:
            self.session.commit()
            logging.info(f"Successfully saved {saved_count} products")
        except SQLAlchemyError as e:
            logging.error(f"Error committing changes to database: {str(e)}")
            self.session.rollback()
            return 0

        return saved_count

    def update_existing_products(self, products: List[Dict[str, Any]]) -> int:
        """
        Update only existing products in the database.
        Returns the number of successfully updated products.
        """
        if not products:
            return 0

        updated_count = 0
        
        for product in products:
            try:
                clean_data = self.clean_product_data(product)
                
                # Only update if product exists
                result = self.session.execute(
                    self.products_table.update()
                    .where(self.products_table.c.url == clean_data['url'])
                    .values(**clean_data)
                )
                
                if result.rowcount > 0:
                    updated_count += 1

            except SQLAlchemyError as e:
                logging.error(f"Error updating product {clean_data.get('title')}: {str(e)}")
                self.session.rollback()
                continue

        try:
            self.session.commit()
            logging.info(f"Successfully updated {updated_count} existing products")
        except SQLAlchemyError as e:
            logging.error(f"Error committing updates: {str(e)}")
            self.session.rollback()
            return 0

        return updated_count