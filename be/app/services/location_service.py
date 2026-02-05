"""
Location Service for Domus

Handles geofence entry events and store detection for demo purposes.
Pre-registered store locations with deterministic matching.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class StoreType(str, Enum):
    """Types of stores we monitor."""
    GROCERY = "grocery"
    PHARMACY = "pharmacy"


@dataclass
class DemoStore:
    """Pre-registered demo store location."""
    place_id: str
    name: str
    store_type: StoreType
    latitude: float
    longitude: float
    radius_meters: float = 150.0


# =============================================================================
# Demo Store Registry
# =============================================================================
# Pre-registered geofence locations for the demo.
# In production, this would come from a database or Places API.

DEMO_STORES: dict[str, DemoStore] = {
    # San Francisco demo locations
    "whole_foods_soma": DemoStore(
        place_id="whole_foods_soma",
        name="Whole Foods",
        store_type=StoreType.GROCERY,
        latitude=37.7785,
        longitude=-122.3950,
    ),
    "trader_joes_castro": DemoStore(
        place_id="trader_joes_castro",
        name="Trader Joe's",
        store_type=StoreType.GROCERY,
        latitude=37.7609,
        longitude=-122.4350,
    ),
    "safeway_marina": DemoStore(
        place_id="safeway_marina",
        name="Safeway",
        store_type=StoreType.GROCERY,
        latitude=37.8005,
        longitude=-122.4369,
    ),
    # Demo/test location (use for simulator testing)
    "demo_grocery": DemoStore(
        place_id="demo_grocery",
        name="Whole Foods",  # Generic name for demo
        store_type=StoreType.GROCERY,
        latitude=37.3318,  # Apple Park area (simulator default)
        longitude=-122.0312,
    ),
}


@dataclass
class GeofenceEntry:
    """Event when user enters a geofence."""
    user_id: str
    place_id: str
    timestamp: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LocationService:
    """
    Handles location-based events for the demo.

    Responsibilities:
    - Validate geofence entry events
    - Look up store information
    - Coordinate with notification service
    """

    def __init__(self):
        self._stores = DEMO_STORES

    def get_demo_stores(self) -> list[dict]:
        """
        Get all demo store geofences for iOS registration.

        Returns list of stores with coordinates and radius for CLCircularRegion.
        """
        return [
            {
                "place_id": store.place_id,
                "name": store.name,
                "latitude": store.latitude,
                "longitude": store.longitude,
                "radius": store.radius_meters,
            }
            for store in self._stores.values()
        ]

    def get_store(self, place_id: str) -> Optional[DemoStore]:
        """Look up store by place_id."""
        return self._stores.get(place_id)

    def validate_entry(self, entry: GeofenceEntry) -> Optional[DemoStore]:
        """
        Validate a geofence entry event.

        Returns the store if valid, None otherwise.
        """
        store = self.get_store(entry.place_id)

        if not store:
            logger.warning(f"Unknown place_id: {entry.place_id}")
            return None

        if store.store_type != StoreType.GROCERY:
            logger.debug(f"Ignoring non-grocery store: {store.name}")
            return None

        logger.info(
            f"Valid geofence entry: user={entry.user_id}, "
            f"store={store.name} ({entry.place_id})"
        )
        return store


# Singleton instance
_location_service: Optional[LocationService] = None


def get_location_service() -> LocationService:
    """Get or create the singleton location service."""
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service
