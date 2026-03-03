function transform(input) {
  const payload = input.countries;

  // Format: {country: {t?: string|array, p?: string, c: [{n, y, x, z?, t?, p?}]}}
  // t can be a string, or an array of strings / {t, p?} objects (multiple toast options)
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

  function pickToast(t, p) {
    if (Array.isArray(t)) {
      if (t.length === 0) return { toast: '', pronunciation: '' };
      const opt = t[Math.floor(Math.random() * t.length)];
      if (typeof opt === 'object' && opt !== null) {
        return { toast: opt.t || '', pronunciation: opt.p || '' };
      }
      return { toast: opt || '', pronunciation: '' };
    }
    return { toast: t || '', pronunciation: p || '' };
  }

  // Shuffle countries for random geographic diversity
  const shuffled = countries.sort(() => Math.random() - 0.5);
  const picked = [];

  for (const country of shuffled) {
    if (picked.length >= 10) break;
    const { t: countryT, p: countryP = '', c: cities } = payload[country];
    const valid = cities.filter(c => c.n && c.y != null && c.x != null);
    if (valid.length === 0) continue;
    const c = valid[Math.floor(Math.random() * valid.length)];
    const rawT = c.t !== undefined ? c.t : countryT;
    const rawP = c.p !== undefined ? c.p : countryP;
    const { toast, pronunciation } = pickToast(rawT, rawP);
    picked.push({
      name:    c.n,
      country,
      lat:     c.y,
      lon:     c.x,
      toast,
      pronunciation,
      zoom:    c.z || 0
    });
  }

  return { data: { cities: picked, count: picked.length } };
}
