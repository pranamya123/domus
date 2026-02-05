/**
 * Parse Gemini fridge response into structured data for card UI
 */

import { FridgeResponseData, InventoryItem, MealSuggestion, RunningLowCategory } from '../components/FridgeResponseCard';

// Check if a message looks like a fridge inventory response
export function isFridgeResponse(content: string): boolean {
  const lowerContent = content.toLowerCase();
  const fridgeKeywords = [
    'fridge',
    'inventory',
    'what\'s in your',
    'here\'s what',
    'you have',
    'items found',
    'cucumbers',
    'vegetables',
    'eggs',
    'cheese',
    'lettuce',
    'tomatoes',
    'meal',
    'recipe',
    'running low',
  ];

  const matchCount = fridgeKeywords.filter(kw => lowerContent.includes(kw)).length;
  return matchCount >= 2;
}

// Parse inventory items from response text
function parseInventoryItems(content: string): InventoryItem[] {
  const items: InventoryItem[] = [];

  // Common patterns for inventory items
  const patterns = [
    /[-•*]\s*\*?\*?([A-Za-z\s]+)\*?\*?[:\s]*(\d+)?/g,
    /(\d+)\s*x?\s*([A-Za-z\s]+)/g,
  ];

  // Try to extract items from bullet points
  const lines = content.split('\n');
  for (const line of lines) {
    const lowerLine = line.toLowerCase();

    // Skip meal suggestion lines
    if (lowerLine.includes('make') || lowerLine.includes('recipe') || lowerLine.includes('suggestion')) {
      continue;
    }

    // Look for common food items
    const foodItems = [
      { name: 'Cucumbers', keywords: ['cucumber'] },
      { name: 'Bell Peppers', keywords: ['pepper', 'bell pepper'] },
      { name: 'Leafy Lettuce', keywords: ['lettuce', 'greens', 'leafy'] },
      { name: 'Cherry Tomatoes', keywords: ['tomato', 'cherry tomato'] },
      { name: 'Yellow Cheese', keywords: ['cheese', 'cheddar'] },
      { name: 'Eggs', keywords: ['egg'] },
      { name: 'Zucchini', keywords: ['zucchini', 'squash'] },
      { name: 'Green Onions', keywords: ['green onion', 'scallion', 'onion'] },
      { name: 'Milk', keywords: ['milk'] },
      { name: 'Butter', keywords: ['butter'] },
      { name: 'Carrots', keywords: ['carrot'] },
      { name: 'Chicken', keywords: ['chicken'] },
      { name: 'Yogurt', keywords: ['yogurt'] },
    ];

    for (const food of foodItems) {
      if (food.keywords.some(kw => lowerLine.includes(kw))) {
        // Extract quantity if present
        const qtyMatch = line.match(/(\d+)/);
        const quantity = qtyMatch ? qtyMatch[1] : '~1';

        // Avoid duplicates
        if (!items.find(i => i.name === food.name)) {
          items.push({
            name: food.name,
            quantity: quantity,
            freshness: 'fresh',
          });
        }
      }
    }
  }

  return items;
}

// Parse meal suggestions from response text
function parseMealSuggestions(content: string): MealSuggestion[] {
  const meals: MealSuggestion[] = [];
  const lowerContent = content.toLowerCase();

  // Common meal patterns to look for
  const mealPatterns = [
    { name: 'Big Fresh Salad', keywords: ['salad', 'fresh salad'] },
    { name: 'Veggie Omelette', keywords: ['omelette', 'omelet', 'scrambled egg'] },
    { name: 'Roasted Veggie Medley', keywords: ['roasted', 'medley', 'roast'] },
    { name: 'Stir Fry', keywords: ['stir fry', 'stir-fry'] },
    { name: 'Vegetable Soup', keywords: ['soup'] },
    { name: 'Pasta Primavera', keywords: ['pasta', 'primavera'] },
    { name: 'Grilled Cheese', keywords: ['grilled cheese'] },
    { name: 'Veggie Wrap', keywords: ['wrap', 'burrito'] },
    { name: 'Frittata', keywords: ['frittata'] },
    { name: 'Buddha Bowl', keywords: ['bowl', 'buddha'] },
  ];

  for (const meal of mealPatterns) {
    if (meal.keywords.some(kw => lowerContent.includes(kw))) {
      if (!meals.find(m => m.name === meal.name)) {
        meals.push({ name: meal.name });
      }
    }
  }

  // If we found any food items but no specific meals, add generic suggestions
  if (meals.length === 0 && lowerContent.includes('meal')) {
    return [
      { name: 'Big Fresh Salad' },
      { name: 'Veggie Omelette' },
      { name: 'Roasted Veggie Medley' },
    ];
  }

  return meals.slice(0, 3);
}

// Parse running low categories
function parseRunningLow(content: string): RunningLowCategory[] {
  const categories: RunningLowCategory[] = [];
  const lowerContent = content.toLowerCase();

  // Check for running low indicators
  if (lowerContent.includes('running low') ||
      lowerContent.includes('might need') ||
      lowerContent.includes('consider getting') ||
      lowerContent.includes('missing') ||
      lowerContent.includes('out of')) {

    // Default categories when running low is mentioned
    categories.push({
      category: 'Proteins',
      items: ['Chicken, fish, beef, tofu', 'Yogurt, cottage cheese'],
    });
    categories.push({
      category: 'Produce',
      items: ['Fruits', 'Cooking onions', 'Fresh herbs'],
    });
    categories.push({
      category: 'Dairy & Pantry',
      items: ['Butter, sour cream', 'Bread, grains', 'Oil, condiments'],
    });
  }

  return categories;
}

// Main parse function
export function parseFridgeResponse(content: string): FridgeResponseData | null {
  if (!isFridgeResponse(content)) {
    return null;
  }

  const inventory = parseInventoryItems(content);
  const meals = parseMealSuggestions(content);
  const runningLow = parseRunningLow(content);

  // Only return data if we found something meaningful
  if (inventory.length === 0 && meals.length === 0 && runningLow.length === 0) {
    return null;
  }

  return {
    inventory: inventory.length > 0 ? inventory : undefined,
    meals: meals.length > 0 ? meals : undefined,
    runningLow: runningLow.length > 0 ? runningLow : undefined,
  };
}

// Demo data for testing the card UI
export function getDemoFridgeData(): FridgeResponseData {
  return {
    inventory: [
      { name: 'Cucumbers', quantity: '5', freshness: 'fresh' },
      { name: 'Bell Peppers', quantity: '3', freshness: 'fresh' },
      { name: 'Leafy Lettuce', quantity: 'head', freshness: 'fresh' },
      { name: 'Cherry Tomatoes', quantity: '10-15', freshness: 'fresh' },
      { name: 'Yellow Cheese', quantity: '1 block', freshness: 'fresh' },
      { name: 'Eggs', quantity: '12', freshness: 'fresh' },
      { name: 'Zucchini', quantity: '~6', freshness: 'fresh' },
      { name: 'Green Onions', quantity: 'bunch', freshness: 'fresh' },
    ],
    meals: [
      { name: 'Big Fresh Salad' },
      { name: 'Veggie Omelette' },
      { name: 'Roasted Veggie Medley' },
    ],
    runningLow: [
      {
        category: 'Proteins',
        items: ['Chicken, fish, beef, tofu', 'Yogurt, cottage cheese'],
      },
      {
        category: 'Produce',
        items: ['Fruits', 'Cooking onions', 'Fresh herbs'],
      },
      {
        category: 'Dairy & Pantry',
        items: ['Butter, sour cream', 'Bread, grains', 'Oil, condiments'],
      },
    ],
  };
}
