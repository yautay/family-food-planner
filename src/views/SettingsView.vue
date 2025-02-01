<template>
  <div class="settings">
    <h1>Settings</h1>
    <ul>
      <li>
        <router-link to="/settings/units">
          <button>Go to Units</button>
        </router-link>
      </li>
      <li>
        <router-link to="/settings/tags">
          <button>Go to Tags</button>
        </router-link>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.settings {
  padding: 20px;
}

ul {
  list-style-type: none;
  padding: 0;
}

li {
  margin-bottom: 10px;
}

button {
  padding: 10px 20px;
  font-size: 16px;
  cursor: pointer;
}
</style>
