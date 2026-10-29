export function validateEventForm({ date, guests, budget }) {
  if (!date) return 'Choose an event date.';
  const guestCount = Number(guests);
  if (!Number.isInteger(guestCount) || guestCount < 1 || guestCount > 50000) {
    return 'Guest count must be a whole number from 1 to 50,000.';
  }
  if (!Number.isFinite(Number(budget)) || Number(budget) <= 0) {
    return 'Enter a budget greater than zero.';
  }
  return null;
}

export function calculateBudget(costs, budget) {
  const spent = Object.values(costs).reduce((sum, amount) => sum + Number(amount || 0), 0);
  return { spent, remaining: Number(budget || 0) - spent };
}

export function toggleTask(tasks, index) {
  return tasks.map((task, taskIndex) => taskIndex === index ? { ...task, done: !task.done } : task);
}

export function updateVendor(vendors, category, updates) {
  return vendors.map(vendor => vendor.category === category ? { ...vendor, ...updates } : vendor);
}

export function upsertPlan(plans, plan) {
  return [plan, ...plans.filter(saved => saved.id !== plan.id)];
}

export function readSavedPlans(storage) {
  try {
    const parsed = JSON.parse(storage.getItem('celebrai-plans') || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
