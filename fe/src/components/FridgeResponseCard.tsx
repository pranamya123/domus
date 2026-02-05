/**
 * Fridge Response Card - Premium card-based UI for fridge inventory
 */

import React from 'react';

export interface InventoryItem {
  name: string;
  quantity: string;
  freshness: 'fresh' | 'expiring' | 'expired';
  image?: string;
}

export interface MealSuggestion {
  name: string;
  image?: string;
}

export interface RunningLowCategory {
  category: string;
  items: string[];
  image?: string;
}

export interface FridgeResponseData {
  inventory?: InventoryItem[];
  meals?: MealSuggestion[];
  runningLow?: RunningLowCategory[];
}

// High-quality food images mapped to specific items
const ITEM_IMAGES: Record<string, string> = {
  // Vegetables
  cucumber: 'https://images.unsplash.com/photo-1449300079323-02e209d9d3a6?w=400&q=80',
  'bell pepper': 'https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?w=400&q=80',
  lettuce: 'https://images.unsplash.com/photo-1622206151226-18ca2c9ab4a1?w=400&q=80',
  tomato: 'https://images.unsplash.com/photo-1546470427-227c7369a9b8?w=400&q=80',
  zucchini: 'https://images.unsplash.com/photo-1563252722-6434563a985d?w=400&q=80',
  'green onion': 'https://images.unsplash.com/photo-1590165482129-1b8b27698780?w=400&q=80',
  carrot: 'https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?w=400&q=80',
  broccoli: 'https://images.unsplash.com/photo-1459411552884-841db9b3cc2a?w=400&q=80',
  spinach: 'https://images.unsplash.com/photo-1576045057995-568f588f82fb?w=400&q=80',

  // Dairy & Proteins
  cheese: 'https://images.unsplash.com/photo-1486297678162-eb2a19b0a32d?w=400&q=80',
  eggs: 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=400&q=80',
  milk: 'https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&q=80',
  butter: 'https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=400&q=80',
  yogurt: 'https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400&q=80',
  chicken: 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400&q=80',

  // Meals
  salad: 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400&q=80',
  omelette: 'https://images.unsplash.com/photo-1525351484163-7529414344d8?w=400&q=80',
  'roasted veggie': 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&q=80',
  stir: 'https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=400&q=80',
  soup: 'https://images.unsplash.com/photo-1547592166-23ac45744acd?w=400&q=80',
  pasta: 'https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=400&q=80',

  // Categories
  proteins: 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400&q=80',
  produce: 'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=400&q=80',
  dairy: 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=400&q=80',
  pantry: 'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400&q=80',
};

// TODO: Integrate with Gemini image generation for unknown items
function getItemImage(name: string): string | null {
  const lower = name.toLowerCase();
  for (const [key, url] of Object.entries(ITEM_IMAGES)) {
    if (lower.includes(key)) return url;
  }
  // Return null if no matching image found
  return null;
}

// Inventory item card
function InventoryCard({ item }: { item: InventoryItem }) {
  const dotColor = item.freshness === 'fresh' ? '#22C55E' : item.freshness === 'expiring' ? '#F59E0B' : '#EF4444';
  const imageUrl = item.image || getItemImage(item.name);

  return (
    <div style={styles.inventoryCard}>
      {/* Only show image if we have a valid URL */}
      {imageUrl ? (
        <img src={imageUrl} alt={item.name} style={styles.inventoryImg} />
      ) : (
        <div style={styles.inventoryImgPlaceholder} />
      )}
      <div style={styles.inventoryMeta}>
        <div style={styles.inventoryNameRow}>
          <svg style={styles.checkIcon} viewBox="0 0 16 16" fill="#22C55E">
            <path d="M8 0a8 8 0 1 0 8 8A8 8 0 0 0 8 0zm3.78 6.28l-4.5 4.5a.75.75 0 0 1-1.06 0l-2-2a.75.75 0 1 1 1.06-1.06L6.75 9.19l3.97-3.97a.75.75 0 1 1 1.06 1.06z"/>
          </svg>
          <span style={styles.inventoryName}>{item.name}</span>
        </div>
        <div style={styles.freshnessRow}>
          <span style={styles.freshLabel}>Fresh</span>
          <span style={{ ...styles.dot, backgroundColor: dotColor }} />
          <span style={styles.qtyLabel}>{item.quantity}</span>
        </div>
      </div>
    </div>
  );
}

// Meal card
function MealCard({ meal }: { meal: MealSuggestion }) {
  const imageUrl = meal.image || getItemImage(meal.name);
  return (
    <div style={styles.mealCard}>
      {imageUrl ? (
        <img src={imageUrl} alt={meal.name} style={styles.mealImg} />
      ) : (
        <div style={styles.mealImgPlaceholder} />
      )}
      <span style={styles.mealName}>{meal.name}</span>
    </div>
  );
}

// Running low category card (text only, no images)
function LowCard({ category }: { category: RunningLowCategory }) {
  return (
    <div style={styles.lowCard}>
      <span style={styles.lowTitle}>{category.category}</span>
      <ul style={styles.lowList}>
        {category.items.map((item, i) => (
          <li key={i} style={styles.lowItem}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}

export function FridgeResponseCard({ data }: { data: FridgeResponseData }) {
  // Filter inventory to only show items with valid images
  const inventoryWithImages = data.inventory?.filter(item => {
    const imageUrl = item.image || getItemImage(item.name);
    return imageUrl !== null;
  }) || [];

  return (
    <div style={styles.wrapper}>
      {/* Inventory */}
      {inventoryWithImages.length > 0 && (
        <div style={styles.section}>
          <span style={styles.sectionTitle}>Inventory</span>
          <div style={styles.inventoryGrid}>
            {inventoryWithImages.slice(0, 8).map((item, i) => (
              <InventoryCard key={i} item={item} />
            ))}
          </div>
        </div>
      )}

      {/* Meals */}
      {data.meals && data.meals.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionHeader}>
            <span style={styles.sectionTitle}>You can make these meals</span>
            <span style={styles.emoji}>🥗</span>
          </div>
          <div style={styles.mealsRow}>
            {data.meals.slice(0, 3).map((meal, i) => (
              <MealCard key={i} meal={meal} />
            ))}
          </div>
        </div>
      )}

      {/* Running Low */}
      {data.runningLow && data.runningLow.length > 0 && (
        <div style={styles.section}>
          <span style={styles.runningLowTitle}>You might be running low on some basics</span>
          <div style={styles.lowGrid}>
            {data.runningLow.map((cat, i) => (
              <LowCard key={i} category={cat} />
            ))}
          </div>
        </div>
      )}

      {/* Follow-up prompt */}
      <div style={styles.followUpSection}>
        <span style={styles.followUpText}>
          Would you like me to suggest a recipe or help you order the missing items?
        </span>
      </div>
    </div>
  );
}

const styles: { [key: string]: React.CSSProperties } = {
  wrapper: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    width: '100%',
  },
  section: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '14px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    marginBottom: '10px',
  },
  sectionTitle: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '15px',
    fontWeight: 600,
    color: '#1a1a1a',
    marginBottom: '10px',
    display: 'block',
  },
  runningLowTitle: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '15px',
    fontWeight: 600,
    color: '#1a1a1a',
    marginBottom: '16px',
    display: 'block',
  },
  emoji: {
    fontSize: '15px',
    marginBottom: '10px',
  },

  // Inventory
  inventoryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '8px',
  },
  inventoryCard: {
    backgroundColor: '#F7F8F9',
    borderRadius: '10px',
    overflow: 'hidden',
  },
  inventoryImg: {
    width: '100%',
    height: '52px',
    objectFit: 'cover',
  },
  inventoryImgPlaceholder: {
    width: '100%',
    height: '52px',
    backgroundColor: '#E8E8E8',
  },
  checkIcon: {
    width: '14px',
    height: '14px',
    flexShrink: 0,
  },
  inventoryMeta: {
    padding: '6px 8px 8px',
  },
  inventoryNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '3px',
    marginBottom: '2px',
  },
  inventoryName: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '11px',
    fontWeight: 500,
    color: '#1a1a1a',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  freshnessRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '3px',
  },
  freshLabel: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '9px',
    color: '#888',
  },
  dots: {
    display: 'flex',
    gap: '2px',
  },
  dot: {
    width: '5px',
    height: '5px',
    borderRadius: '50%',
  },
  qtyLabel: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '9px',
    color: '#888',
    marginLeft: '2px',
  },

  // Meals
  mealsRow: {
    display: 'flex',
    gap: '8px',
  },
  mealCard: {
    flex: 1,
    minWidth: 0,
  },
  mealImg: {
    width: '100%',
    height: '72px',
    objectFit: 'cover',
    borderRadius: '10px',
    marginBottom: '6px',
  },
  mealImgPlaceholder: {
    width: '100%',
    height: '72px',
    backgroundColor: '#E8E8E8',
    borderRadius: '10px',
    marginBottom: '6px',
  },
  mealName: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '11px',
    fontWeight: 500,
    color: '#1a1a1a',
    textAlign: 'center' as const,
    display: 'block',
  },

  // Running Low
  lowGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '8px',
  },
  lowCard: {
    backgroundColor: '#F7F8F9',
    borderRadius: '10px',
    padding: '12px',
  },
  lowTitle: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '12px',
    fontWeight: 600,
    color: '#1a1a1a',
    display: 'block',
    marginBottom: '4px',
  },
  lowList: {
    margin: 0,
    padding: 0,
    listStyle: 'none',
  },
  lowItem: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '11px',
    color: '#666',
    lineHeight: 1.6,
  },

  // Follow-up prompt
  followUpSection: {
    backgroundColor: '#DAF7DA',
    borderRadius: '14px',
    padding: '14px 16px',
  },
  followUpText: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '14px',
    color: '#1a1a1a',
    lineHeight: 1.5,
  },
};

export default FridgeResponseCard;
