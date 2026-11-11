/* Retired workshop URLs retain only this forwarding entry, never the old UI. */
(function () {
  'use strict';
  var query = new URLSearchParams(location.search);
  var character = query.get('character');
  var gate = query.get('gate');
  var oldHash = /^#(?:char|c)\/([^/]+)$/.exec(location.hash || '');
  if (!character && oldHash) {
    try { character = decodeURIComponent(oldHash[1]); } catch (_) { character = null; }
  }
  var target = '/studio/factory.html#all';
  if (character && gate && /^G[0-9]+[a-z]?$/.test(gate)) {
    target = '/gate.html?character=' + encodeURIComponent(character) + '&gate=' + encodeURIComponent(gate);
  } else if (character) {
    target = '/studio/factory.html#c/' + encodeURIComponent(character);
  }
  location.replace(target);
})();
