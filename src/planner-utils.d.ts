export function validateEventForm(input: { date: string; guests: string | number; budget: string | number }): string | null;
export function calculateBudget(costs: Record<string, number>, budget: number): { spent: number; remaining: number };
export function toggleTask<T extends { done: boolean }>(tasks: T[], index: number): T[];
export function updateVendor<T extends { category: string }>(vendors: T[], category: string, updates: Partial<T>): T[];
export function upsertPlan<T extends { id: string }>(plans: T[], plan: T): T[];
export function readSavedPlans(storage: Pick<Storage, 'getItem'>): unknown[];
