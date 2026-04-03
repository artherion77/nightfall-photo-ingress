<script>
  export let error;
</script>

<h1>Something went wrong</h1>
<p>{error?.message ?? 'Unknown error'}</p>
