<script>
  import { page } from '$app/stores';
</script>

<h1>Something went wrong</h1>
<p>{$page.error?.message ?? 'Unknown error'}</p>
