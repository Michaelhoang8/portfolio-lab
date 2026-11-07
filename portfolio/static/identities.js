/* App identities are keyed to the same mode as the functional workspace. */
window.designIdentity = function (app) {
  const identities = {
    tickets: ['Issue Desk', 'DELIVERY / TEAM WORKSPACE', 'Keep the next release moving.'],
    inventory: ['Stockroom', 'OPERATIONS / GOODS IN MOTION', 'Every item. Every movement. Accounted for.'],
    experiments: ['Experiment Studio', 'RESEARCH / A–B TESTING', 'Turn a hypothesis into a measured decision.'],
    profile: ['Dataset Explorer', 'DATA INSPECTION / 01', 'Know what is in your data before you build on it.'],
    clean: ['Pipeline Studio', 'TRANSFORM / VALIDATE / EXPORT', 'A repeatable path from raw rows to usable data.'],
    sales: ['Revenue Lens', 'THE REVENUE REPORT', 'Follow the numbers. Find the story behind the sale.'],
    logs: ['Auth Watch', 'SECURITY OPERATIONS / EVENT TRIAGE', 'Find suspicious patterns in authentication events.'],
    headers: ['Header Review', 'WEB SECURITY / FIELD GUIDE', 'A practical checklist for your HTTP response headers.'],
    secrets: ['Secret Sentinel', 'PRIVATE CODE REVIEW', 'Catch exposed credentials before they travel further.'],
    train: ['Classifier Lab', 'NOTEBOOK 01 / SUPERVISED LEARNING', 'Train a baseline. Inspect the evidence. Repeat.'],
    search: ['Retrieval Studio', 'A SMALL LIBRARY, MADE SEARCHABLE', 'Ask a question. Discover the passages that matter.'],
    evaluate: ['Model Observatory', 'MEASUREMENT / CLASSIFICATION', 'Accuracy is only the beginning of the story.'],
    manifest: ['Manifest Review', 'INFRASTRUCTURE / CONFIGURATION REVIEW', 'Inspect the configuration before it becomes infrastructure.'],
    pipeline: ['Pipeline Planner', 'BUILD → TEST → SHIP', 'See how jobs connect and where time goes.'],
    reliability: ['Reliability Desk', 'SERVICE HEALTH / ERROR BUDGETS', 'Know how much room your service has left.'],
    rest: ['REST Studio', 'HTTP / REQUEST + RESPONSE', 'Work directly with the contract. Inspect every response.']
  };
  const identity = identities[app];
  if (!identity) return;
  document.body.dataset.app = app;
  document.title = `${identity[0]} · Portfolio Lab`;
  const intro = document.querySelector('.intro');
  if (intro) {
    intro.querySelector('h1').textContent = identity[0];
    intro.querySelector('.eyebrow').textContent = identity[1];
    intro.querySelector('p:not(.eyebrow)').textContent = identity[2];
    const brand = document.querySelector('header a:first-child');
    brand.textContent = '← Portfolio Lab';
  }
};
document.addEventListener('DOMContentLoaded', () => {
  if (location.pathname === '/rest') window.designIdentity('rest');
});
