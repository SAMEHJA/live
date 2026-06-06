from Common import search_imdbapi_dev, get_tmdb_details, get_imdb_details

title = "The Batman"
year = "2022"

print("Testing IMDBAPI.dev...")
rating, votes = search_imdbapi_dev(title, year)
print(f"IMDBAPI.dev: rating={rating}, votes={votes}")

print("\nTesting TMDb...")
rating, votes = get_tmdb_details(title, year, "movie")
print(f"TMDb: rating={rating}, votes={votes}")

print("\nTesting OMDb...")
rating, votes, _, _ = get_imdb_details(title, year, "movie")
print(f"OMDb: rating={rating}, votes={votes}")