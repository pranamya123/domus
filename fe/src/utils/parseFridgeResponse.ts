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

// Parse inventory items from response text - ONLY from structured sections
function parseInventoryItems(content: string): InventoryItem[] {
  const items: InventoryItem[] = [];

  // Only parse inventory from explicit INVENTORY section - progressive disclosure
  const inventorySection = content.match(/###?\s*INVENTORY\s*\n+([\s\S]*?)(?=\n###|\n##|$)/i);
  if (!inventorySection) {
    // No explicit inventory section = no inventory to show
    return [];
  }

  const inventorySectionContent = inventorySection[1];
  const lines = inventorySectionContent.split('\n');

  // Look for common food items within the inventory section only
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

  for (const line of lines) {
    const lowerLine = line.toLowerCase();

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

// Parse meal suggestions from response text - ONLY from structured sections
function parseMealSuggestions(content: string): MealSuggestion[] {
  const meals: MealSuggestion[] = [];

  // Only parse meals from explicit MEALS section - progressive disclosure
  const mealsSection = content.match(/###?\s*MEALS?\s*\n+([\s\S]*?)(?=\n###|\n##|$)/i);
  if (!mealsSection) {
    // No explicit meals section = no meals to show
    return [];
  }

  const mealsSectionContent = mealsSection[1];

  // Common meal patterns to look for within the meals section only
  const mealPatterns = [
    { name: 'Big Fresh Salad', keywords: ['salad', 'fresh salad', 'garden salad'] },
    { name: 'Veggie Omelette', keywords: ['omelette', 'omelet', 'scrambled egg'] },
    { name: 'Roasted Veggie Medley', keywords: ['roasted', 'medley', 'roast'] },
    { name: 'Stir-Fry', keywords: ['stir fry', 'stir-fry', 'stirfry'] },
    { name: 'Vegetable Soup', keywords: ['soup'] },
    { name: 'Pasta Primavera', keywords: ['pasta', 'primavera'] },
    { name: 'Grilled Cheese', keywords: ['grilled cheese'] },
    { name: 'Veggie Wrap', keywords: ['wrap', 'burrito'] },
    { name: 'Frittata', keywords: ['frittata'] },
    { name: 'Buddha Bowl', keywords: ['bowl', 'buddha'] },
  ];

  const lowerSection = mealsSectionContent.toLowerCase();
  for (const meal of mealPatterns) {
    if (meal.keywords.some(kw => lowerSection.includes(kw))) {
      if (!meals.find(m => m.name === meal.name)) {
        meals.push({ name: meal.name });
      }
    }
  }

  return meals.slice(0, 3);
}

// Parse running low categories - ONLY from structured sections
function parseRunningLow(content: string): RunningLowCategory[] {
  const categories: RunningLowCategory[] = [];

  // Only parse from explicit RUNNING_LOW section - progressive disclosure
  const runningLowSection = content.match(/###?\s*RUNNING[_\s]?LOW\s*\n+([\s\S]*?)(?=\n###|\n##|$)/i);
  if (!runningLowSection) {
    // No explicit running low section = don't show it
    return [];
  }

  const sectionContent = runningLowSection[1].toLowerCase();

  // Parse categories from the section
  if (sectionContent.includes('protein')) {
    categories.push({
      category: 'Proteins',
      items: ['Chicken, fish, beef, tofu'],
    });
  }
  if (sectionContent.includes('produce') || sectionContent.includes('vegetable') || sectionContent.includes('fruit')) {
    categories.push({
      category: 'Produce',
      items: ['Fresh fruits', 'Cooking onions', 'Fresh herbs'],
    });
  }
  if (sectionContent.includes('dairy') || sectionContent.includes('pantry')) {
    categories.push({
      category: 'Dairy & Pantry',
      items: ['Butter, cream', 'Bread, grains'],
    });
  }

  return categories;
}

// Parse insight section from Gemini response (judgment-first with progressive disclosure)
function parseInsight(content: string): string | undefined {
  // Look for INSIGHT section header
  const insightMatch = content.match(/###?\s*INSIGHT\s*\n+([\s\S]*?)(?=\n###|\n##|$)/i);
  if (insightMatch && insightMatch[1]) {
    return insightMatch[1].trim();
  }

  // Progressive disclosure format: entire response is insight + question (no structured sections)
  const firstHeaderIndex = content.search(/\n###?\s/);
  if (firstHeaderIndex === -1) {
    // No headers found - entire response is the insight (judgment + follow-up question)
    const cleaned = content.replace(/\*\*/g, '').trim();
    if (cleaned.length > 30 && !cleaned.startsWith('#') && !cleaned.startsWith('-')) {
      return cleaned;
    }
  } else if (firstHeaderIndex > 50) {
    // Has headers but preamble exists - extract preamble as insight
    const preamble = content.substring(0, firstHeaderIndex).trim();
    if (preamble && !preamble.startsWith('#') && !preamble.startsWith('-') && !preamble.startsWith('*')) {
      const cleaned = preamble.replace(/\*\*/g, '').trim();
      if (cleaned.length > 30) {
        return cleaned;
      }
    }
  }

  // Fallback: Look for judgment-style opening sentences
  const lines = content.split('\n').filter(line => line.trim());
  const insightLines: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim().replace(/\*\*/g, '');
    // Stop at headers or lists
    if (trimmed.startsWith('#') || trimmed.startsWith('-') || trimmed.startsWith('*') || trimmed.startsWith('•')) {
      break;
    }
    // Skip old-style headers
    if (trimmed.toLowerCase().includes("here's what") || trimmed.includes('👀') || trimmed.toLowerCase().includes("i can see")) {
      continue;
    }
    // Collect judgment-style content
    if (trimmed.length > 20) {
      insightLines.push(trimmed);
    }
  }

  if (insightLines.length > 0) {
    return insightLines.join('\n\n');
  }

  return undefined;
}

// Main parse function
export function parseFridgeResponse(content: string): FridgeResponseData | null {
  if (!isFridgeResponse(content)) {
    return null;
  }

  const insight = parseInsight(content);
  const inventory = parseInventoryItems(content);
  const meals = parseMealSuggestions(content);
  const runningLow = parseRunningLow(content);

  // Progressive disclosure: insight-only responses are valid
  // Return data if we have insight OR structured content
  if (!insight && inventory.length === 0 && meals.length === 0 && runningLow.length === 0) {
    return null;
  }

  return {
    insight,
    inventory: inventory.length > 0 ? inventory : undefined,
    meals: meals.length > 0 ? meals : undefined,
    runningLow: runningLow.length > 0 ? runningLow : undefined,
  };
}

// Demo data for testing the card UI (progressive disclosure - insight only)
export function getDemoFridgeData(): FridgeResponseData {
  return {
    insight: "You have enough ingredients for a quick dinner tonight, but you're low on fresh produce for the rest of the week. The eggs and vegetables can handle tonight's stir-fry, but you'll want to restock proteins by Wednesday.\n\nWould you like to see what's in your inventory, or get meal ideas for tonight?",
  };
}

// Full inventory data (shown only when user asks)
export function getFullInventoryData(): FridgeResponseData {
  return {
    inventory: [
      { name: 'Cucumbers', quantity: '5', freshness: 'fresh' },
      { name: 'Bell Peppers', quantity: '3', freshness: 'fresh' },
      { name: 'Leafy Lettuce', quantity: 'head', freshness: 'fresh' },
      { name: 'Yellow Cheese', quantity: '1 block', freshness: 'fresh' },
      { name: 'Eggs', quantity: '12', freshness: 'fresh' },
      { name: 'Zucchini', quantity: '~6', freshness: 'fresh' },
      { name: 'Green Onions', quantity: 'bunch', freshness: 'fresh' },
      { name: 'Milk', quantity: '1 gallon', freshness: 'fresh' },
    ],
  };
}

// Meal ideas data (shown only when user asks)
export function getMealIdeasData(): FridgeResponseData {
  return {
    meals: [
      { name: 'Big Fresh Salad' },
      { name: 'Veggie Omelette' },
      { name: 'Stir-Fry' },
    ],
  };
}
