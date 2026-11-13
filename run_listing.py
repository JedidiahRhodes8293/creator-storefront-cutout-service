import os
import sys

from src.listing_service import InfraiClient, image_from_file, process_listing


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python run_listing.py IMAGE_PATH BUCKET")
    api_key = os.environ["INFRAI_API_KEY"]
    client = InfraiClient(api_key)
    bucket = sys.argv[2]
    client.create_bucket(bucket)
    result = process_listing(client, image_from_file(sys.argv[1]), bucket, subscribers=1)
    if result is None:
        print("Listing stays in draft because there are no subscribers.")
        return
    print(f"Cutout ready: {result.object_key}")
    print(f"Download URL: {result.download_url}")


if __name__ == "__main__":
    main()
