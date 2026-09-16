"""Write a code to identify palindrom handle edge cases"""
def is_palindrome(s):
    return s == s[::-1]

# Test cases
print(is_palindrome("radar"))  # True
print(is_palindrome("python"))  # False
print(is_palindrome("level"))  # True
print(is_palindrome(""))  # False
print(is_palindrome("a man a plan a canal Panama"))  # True
print(is_palindrome("Was it a car or a cat I saw"))  # True
print(is_palindrome("No 'x' in Nixon"))  # Trueprint(is_palindrome("Madam"))  # True
print(is_palindrome("12321"))  # True
print(is_palindrome("123456"))  # False
print(is_palindrome("123456789"))  # False
print(is_palindrome("12345678934567890"))  # False
print(is_palindrome("123456789012345678901234567890"))  # False
print(is_palindrome("123456789012345678901234567890123456789012345678901234567890"))  # Falseprint(is_palindrome("123456789012345678901234567890123456789012

