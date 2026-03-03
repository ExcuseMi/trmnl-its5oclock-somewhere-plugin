function transform(input) {
  const payload = input.data;

  // Format: {country: {t?: toast, p?: pronunciation, c: [{n, y, x, z?, t?, p?}]}}
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { data: { cities: [], count: 0 } };
  }

  const countries = Object.keys(payload).filter(k => {
    const v = payload[k];
    return v && Array.isArray(v.c) && v.c.length > 0;
  });

  if (countries.length === 0) {
    return { data: { cities: [], count: 0 } };
  }

  // Shuffle countries for random geographic diversity
  const shuffled = countries.sort(() => Math.random() - 0.5);
  const picked = [];

  for (const country of shuffled) {
    if (picked.length >= 10) break;
    const { t: countryToast = '', p: countryPron = '', c: cities } = payload[country];
    const valid = cities.filter(c => c.n && c.y != null && c.x != null);
    if (valid.length === 0) continue;
    const c = valid[Math.floor(Math.random() * valid.length)];
    picked.push({
      name:          c.n,
      country,
      lat:           c.y,
      lon:           c.x,
      toast:         c.t || countryToast,
      pronunciation: c.p || countryPron,
      zoom:          c.z || 0
    });
  }

  return { data: { cities: picked, count: picked.length } };
}
