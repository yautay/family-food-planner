<template>
  <section class="surface-card">
    <div class="content mb-4">
      <h1>Planowanie diety dla calej rodziny</h1>
      <p>
        Tworz harmonogram posilkow, korzystaj ze wspolnego katalogu przepisow i generuj liste zakupow
        gotowa do sklepu.
      </p>
    </div>

    <div class="columns is-multiline">
      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/catalog" class="box is-block">
          <h2 class="title is-5 mb-2">Katalog</h2>
          <p class="is-size-6 has-text-grey">
            Przegladaj produkty i przepisy. Dane zaimportowane z PDF sa publiczne i tylko do odczytu.
          </p>
        </RouterLink>
      </div>

      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/ingredients" class="box is-block">
          <h2 class="title is-5 mb-2">Skladniki</h2>
          <p class="is-size-6 has-text-grey">
            Zarzadzaj lista skladnikow oraz ich parametrami odzywczymi (wymaga uprawnien).
          </p>
        </RouterLink>
      </div>

      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/settings" class="box is-block">
          <h2 class="title is-5 mb-2">Ustawienia</h2>
          <p class="is-size-6 has-text-grey">
            Jednostki, tagi, preferencje interfejsu oraz konfiguracja konta.
          </p>
        </RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'
</script>
