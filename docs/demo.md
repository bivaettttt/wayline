# Wayline demo / Демонстрация

1. Запустите `scripts/lab up`. Под `traveler` создайте поездку из `WL101` и `WL202`. В Стамбуле плановый интервал составляет 95 минут.
2. Под `admin` запустите «Риск пересадки» с флажком «Оставить задержку после проверки риска». Lab передаст независимому провайдеру задержку в 60 минут. Сравните сохранённые плановые 95 минут, прогнозные 35 и MCT 60. В ответе эксперимента остаются реальные оценки и подбор. Сценарий «Восстановление планового прогноза» возвращает маршрут к исходному прогнозу.
3. Откройте журнал событий и уведомления. Проверьте источник, порядковый номер и версию рейса. В карточке поездки сравните альтернативы.
4. Для технической демонстрации запустите «Конфликт версий», «Дубликат события», «Недоступность провайдера» и «Изменилось расписание». Укажите, при каких условиях сохраняется курсор и когда снимок маршрутов теряет актуальность.
5. Для демонстрации жизненного цикла выполните «Отмена рейса» и примите нарушение к сведению под `traveler`.

| Экран | Снимок |
| --- | --- |
| Обзор | [Dashboard](../assets/screenshots/dashboard.png) |
| Поездки | [Trips](../assets/screenshots/trips.png) |
| Карточка поездки | [Trip details](../assets/screenshots/trip.png) |
| Сборка маршрута | [Builder](../assets/screenshots/builder.png) |
| История рейса | [Flight timeline](../assets/screenshots/flight.png) |
| Оценка пересадки | [Connection assessment](../assets/screenshots/connection.png) |
| Центр нарушений | [Disruption center](../assets/screenshots/disruptions.png) |
| Нарушение | [Disruption details](../assets/screenshots/disruption-details.png) |
| Варианты | [Alternative routes](../assets/screenshots/alternatives.png) |
| Сравнение | [Comparison](../assets/screenshots/comparison.png) |
| Провайдер | [Provider monitoring](../assets/screenshots/provider.png) |
| Журнал событий | [Events](../assets/screenshots/events.png) |
| Уведомления | [Notifications](../assets/screenshots/notifications.png) |
| Лаборатория | [Lab](../assets/screenshots/lab.png) |

[Запись двух сквозных прогонов Playwright](../assets/demo/wayline.mp4). Кадры сняты с рабочего Compose-окружения на синтетических данных.
