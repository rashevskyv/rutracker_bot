# План впровадження — Додавання релізів delsonazevedo

Цей план описує додавання 7 Switch портів від автора delsonazevedo до черги ручних релізів (`data/manual_releases.json`) та оновлення назв наявних релізів для ігор з тих самих серій (Zelda та Castlevania) з метою зазначення авторів.

## Необхідно уточнити у користувача

> [!IMPORTANT]
> **Питання про збирання програми:**
> Чи потрібно мені збирати самостійну програму (білд/пакет) після того, як я закінчу вносити зміни, чи ви хочете зробити це вручну?
> *(Будь ласка, оберіть варіант у вашій відповіді).*

## Пропоновані зміни

### Реєстр ручних релізів (`data/manual_releases.json`)

Ми додамо наступні нові релізи від `delsonazevedo`:
1. **Zelda: Link's Awakening DX HD (delsonazevedo)** (версія 1.7.3)
2. **Celeste 64** (версія 1.1.1)
3. **BattleShip** (версія 1.3)
4. **Starship** (версія 2.0.0)
5. **Castlevania: ReVamped - Open Source Edition (delsonazevedo)** (версія v1.0.0)
6. **Crazy Taxi NX** (версія 1.0.0)
7. **OpenBOR** (версія v3.0.7141)

Оскільки серії ігор **Zelda** та **Castlevania** вже представлені в нашому реєстрі, ми оновимо назви існуючих релізів цих ігор, щоб додати ім'я автора для кращої ідентифікації:
- `Castlevania: Order of Ecclesia` ➔ `Castlevania: Order of Ecclesia (Black Dragon Studio)`
- `Castlevania: Dawn of Sorrow` ➔ `Castlevania: Dawn of Sorrow (Black Dragon Studio)`
- `Sotn NX (Castlevania: Symphony of the Night)` ➔ `Sotn NX (Castlevania: Symphony of the Night) (NaGaa95)`
- `The Legend of Zelda: The Minish Cap` ➔ `The Legend of Zelda: The Minish Cap (ZeldaMC)`
- `dusklight (Zelda: Twilight Princess від HayatoG` ➔ `dusklight (Zelda: Twilight Princess) (HayatoG)`
- `tmc (Zelda: Minish Cap)` ➔ `tmc (Zelda: Minish Cap) (HayatoG)`

## План верифікації

### Ручна перевірка
1. Запуск скрипта автоматичної обробки та перевірка коректності структури JSON у `data/manual_releases.json`.
2. Перевірка, що всі 7 релізів додано з відповідними версіями, описами українською мовою (перекладеними через GPT) та правильними прапорцями.
3. Перевірка, що назви існуючих релізів Zelda та Castlevania оновилися з додаванням авторів.
