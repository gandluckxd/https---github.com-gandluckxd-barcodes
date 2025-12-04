"""
Тестовый скрипт для проверки инициализации pygame mixer
"""
import pygame

print("="*60)
print("Тестирование инициализации pygame mixer")
print("="*60)

# Тест 1: Стандартная инициализация
try:
    pygame.mixer.init()
    print("✓ Тест 1 ПРОЙДЕН: Стандартная инициализация")
    pygame.mixer.quit()
except Exception as e:
    print(f"✗ Тест 1 НЕ ПРОЙДЕН: {e}")

    # Тест 2: С параметрами 22050Hz
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        print("✓ Тест 2 ПРОЙДЕН: Инициализация 22050Hz")
        pygame.mixer.quit()
    except Exception as e2:
        print(f"✗ Тест 2 НЕ ПРОЙДЕН: {e2}")

        # Тест 3: С параметрами 44100Hz mono
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=4096)
            print("✓ Тест 3 ПРОЙДЕН: Инициализация 44100Hz mono")
            pygame.mixer.quit()
        except Exception as e3:
            print(f"✗ Тест 3 НЕ ПРОЙДЕН: {e3}")
            print("\n❌ ВСЕ ТЕСТЫ НЕ ПРОЙДЕНЫ - аудио недоступно")
            print("Возможные причины:")
            print("1. Отсутствует аудио устройство")
            print("2. Аудио драйверы не установлены")
            print("3. Аудио устройство используется другим приложением")
            exit(1)

print("\n✓ Тестирование завершено успешно")
print("="*60)
