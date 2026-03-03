function transform(input) {
  const cities = input.data;
  if (!Array.isArray(cities) || cities.length === 0) {
    return { data: { cities: [], count: 0 } };
  }

  const valid = cities.filter(c => c.name && c.lat != null && c.lon != null);
  if (valid.length === 0) {
    return { data: { cities: [], count: 0 } };
  }

  // Prefer one city per country for geographic diversity
  const byCountry = {};
  for (const c of valid) {
    const key = c.country || 'Unknown';
    (byCountry[key] = byCountry[key] || []).push(c);
  }

  const shuffledCountries = Object.keys(byCountry).sort(() => Math.random() - 0.5);
  const picked = [];

  for (const country of shuffledCountries) {
    if (picked.length >= 10) break;
    const pool = byCountry[country];
    picked.push(pool[Math.floor(Math.random() * pool.length)]);
  }

  // Top up to 10 if fewer countries than needed
  if (picked.length < 10) {
    const used = new Set(picked);
    const rest = valid.filter(c => !used.has(c)).sort(() => Math.random() - 0.5);
    for (const c of rest) {
      if (picked.length >= 10) break;
      picked.push(c);
    }
  }

  const result = picked.map(c => ({
    name:     c.name,
    country:  c.country || '',
    lat:      c.lat,
    lon:      c.lon,
    toast:    c.toast || '',
    zoom:     c.zoom || 0,
    maps_url: 'https://www.google.com/maps?q=' + c.lat + ',' + c.lon
  }));

  return { data: { cities: result, count: result.length } };
}
