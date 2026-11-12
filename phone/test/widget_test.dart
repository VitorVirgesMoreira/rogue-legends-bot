import 'package:flutter_test/flutter_test.dart';
import 'package:roguebot_phone/i18n.dart';
import 'package:roguebot_phone/options.dart';

void main() {
  test('every UI text exists in both languages', () {
    expect(texts['es']!.keys.toSet(), texts['en']!.keys.toSet());
  });

  test('a full routine report lists the parts, then the levels', () {
    final report = {
      'results': ['victory', 'defeat', 'victory'],
      'repeat': true,
      'parts': [
        ['vip', 'done'],
        ['raid', 'skipped'],
      ],
    };
    expect(renderReport(report, 'en'), 'VIP cards: done, Guild raid: skipped\nOut of energy after 3 runs: 2 victories, 1 defeats');
    expect(renderReport({'results': ['defeat'], 'repeat': false, 'parts': []}, 'es'), 'Nivel terminado: Derrota');
  });

  test('saved options are restored, invalid ones keep their defaults', () {
    final o = Options()
      ..restore({
        'lang': 'en',
        'mode': 'elite',
        'source': 'nonsense',
        'level': 'x',
        'loop': true,
        'ads': 'yes',
        'damage_order': ['fire', 'ice', 'lightning', 'shuriken', 'venom', 'bleed'],
      });
    expect([o.lang, o.mode, o.source, o.level, o.loop, o.ads], ['en', 'elite', 'latest', '1', true, false]);
    expect(o.toJson().containsKey('repeat'), false);  // only keep running + full routine
    expect(o.order.first, 'fire');
    final bad = Options()..restore({'damage_order': ['fire']});
    expect(bad.order, damageTypes);
  });

  test('options survive a save and restore', () {
    final o = Options()
      ..full = true
      ..supportEvery = '4'
      ..nature = 'magic';
    final copy = Options()..restore(o.toJson());
    expect(copy.toJson(), o.toJson());
  });

  test('malformed options and mixed type orders keep defaults', () {
    for (final raw in ['{', 'null', '[]', '42', '{"damage_order":["fire",3]}', '{"damage_order":"fire"}']) {
      final options = Options()..restoreJson(raw);
      expect(options.toJson(), Options().toJson());
    }
  });

  test('restored damage order is owned by the options', () {
    final saved = [...damageTypes.reversed];
    final options = Options()..restore({'damage_order': saved});
    saved.clear();
    expect(options.order, damageTypes.reversed.toList());
  });
}
