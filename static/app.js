(() => {
  const form = document.getElementById('bid-calculator');
  if (!form) return;

  const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

  function read(name) {
    const value = Number(form.elements[name].value);
    return Number.isFinite(value) ? value : 0;
  }

  function calculate(event) {
    if (event) event.preventDefault();
    const sqft = read('sqft');
    const visitsPerWeek = read('visits');
    const productionRate = Math.max(1, read('rate'));
    const wage = read('wage');
    const burdenRate = read('burden') / 100;
    const suppliesPerVisit = read('supplies');
    const equipment = read('equipment');
    const overheadRate = read('overhead') / 100;
    const marginRate = Math.min(0.9, read('margin') / 100);

    const visitsPerMonth = visitsPerWeek * 52 / 12;
    const laborHours = (sqft / productionRate) * visitsPerMonth;
    const loadedLabor = laborHours * wage * (1 + burdenRate);
    const supplies = suppliesPerVisit * visitsPerMonth;
    const directCost = loadedLabor + supplies + equipment;
    const overhead = directCost * overheadRate;
    const totalCost = directCost + overhead;
    const price = totalCost / Math.max(0.01, 1 - marginRate);
    const profit = price - totalCost;

    document.getElementById('result-price').textContent = money.format(price);
    document.getElementById('result-hours').textContent = number.format(laborHours);
    document.getElementById('result-labor').textContent = money.format(loadedLabor);
    document.getElementById('result-supplies').textContent = money.format(supplies);
    document.getElementById('result-equipment').textContent = money.format(equipment);
    document.getElementById('result-overhead').textContent = money.format(overhead);
    document.getElementById('result-profit').textContent = money.format(profit);
  }

  form.addEventListener('submit', calculate);
  form.addEventListener('input', calculate);
  calculate();
})();
