import json
import sondehub
import argparse

def on_message(message):
    print(json.dumps(message))

def main():
    parser = argparse.ArgumentParser(description='Sondehub CLI')
    parser.add_argument('--serial', dest="sondes", default=["#"],nargs="*", help="Filter to sonde serial", type=str, action="extend")
    args = parser.parse_args()
    if len(args.sondes) > 1: # we need to drop the default value if the user specifies sepcific sondes
        args.sondes = args.sondes[1:]
    test = sondehub.Stream(on_message=on_message, sondes=args.sondes)
    while 1:
        pass

if __name__ == "__main__":
    main()