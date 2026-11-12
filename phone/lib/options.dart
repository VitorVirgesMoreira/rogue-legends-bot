import 'dart:convert';

import 'i18n.dart';

const damageTypes = ['ice', 'lightning', 'fire', 'shuriken', 'venom', 'bleed'];

/// Every option the user sets, saved between sessions (like data/settings.json on the desktop).
class Options {
  String lang = 'es', mode = 'normal', source = 'latest', level = '1', nature = 'physical', supportEvery = '3';
  bool full = false, loop = false, ads = false, support = false;
  List<String> order = [...damageTypes];

  Map<String, Object> toJson() => {
        'lang': lang, 'mode': mode, 'source': source, 'level': level, 'nature': nature, 'support_every': supportEvery,
        'full': full, 'loop': loop, 'ads': ads, 'support': support, 'damage_order': order,
      };

  void restoreJson(String raw) {
    try {
      final data = jsonDecode(raw);
      if (data is Map<String, dynamic>) restore(data);
    } on FormatException {
      // Keep defaults if a previous write was interrupted or edited incorrectly.
    }
  }

  /// Last session's choices; anything missing or invalid keeps its default.
  void restore(Map<String, dynamic> s) {
    T? pick<T>(String key, bool Function(T) ok) => s[key] is T && ok(s[key] as T) ? s[key] as T : null;
    lang = pick<String>('lang', uiLanguages.containsKey) ?? lang;
    mode = pick<String>('mode', ['normal', 'elite'].contains) ?? mode;
    source = pick<String>('source', ['latest', 'beaten', 'pending', 'stars'].contains) ?? source;
    nature = pick<String>('nature', ['physical', 'magic'].contains) ?? nature;
    level = pick<String>('level', (v) => int.tryParse(v) != null) ?? level;
    supportEvery = pick<String>('support_every', (v) => int.tryParse(v) != null) ?? supportEvery;
    full = pick<bool>('full', (_) => true) ?? full;
    loop = pick<bool>('loop', (_) => true) ?? loop;
    ads = pick<bool>('ads', (_) => true) ?? ads;
    support = pick<bool>('support', (_) => true) ?? support;
    final saved = s['damage_order'];
    if (saved is List && saved.length == damageTypes.length && damageTypes.every(saved.contains)) {
      order = List<String>.from(saved);
    }
  }
}

