function transform(input) {
  const cityMatch = input.data.match(/It's 5 o'clock in ([^!]+)!/);
  const urlMatch = input.data.match(/href="(https:\/\/lmddgtfy[^"]+)"/);
  return { data: {
    name: cityMatch ? cityMatch[1].trim() : "",
    url: urlMatch ? urlMatch[1] : ""
  }};
}